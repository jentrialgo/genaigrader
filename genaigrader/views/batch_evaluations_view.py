from django.db.models import Count, Q
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from genaigrader.models import Course, Exam, Model
from django.views.decorators.csrf import csrf_exempt
from django.http import StreamingHttpResponse
from django.utils import timezone
from genaigrader.services.get_models_service import get_models_for_user
from genaigrader.services.stream_service import stream_responses
from genaigrader.llm_api import LlmApi
import logging
import json
from typing import Generator, Iterable, List, Dict, Any

def generate_eval_tasks(exams: Iterable, models: Iterable, repetitions: int) -> Generator:
    """
    Generator that yields all combinations of exams, models, and repetitions.
    Args:
        exams: Iterable of Exam objects.
        models: Iterable of Model objects.
        repetitions: Number of repetitions for each exam-model pair.
    Yields:
        Tuple of (exam, model, repetition number)
    """
    # Models are iterated before exams because loading a local model has
    # a significant overhead, and we want to minimize the number of times
    # we load the model.
    for model in models:
        for exam in exams:
            for rep in range(1, repetitions + 1):
                yield exam, model, rep

def validate_exam(exam: Exam) -> Iterable:
    """
    Validates that the exam has questions.
    Args:
        exam: Exam object to validate.
    Returns:
        Queryset of questions for the exam.
    Raises:
        ValueError: If the exam has no questions.
    """
    questions = exam.question_set.prefetch_related('questionoption_set').all()
    if not questions.exists():
        raise ValueError(f"Exam {exam} has no questions.")
    return questions

def validate_model(model: Model) -> 'LlmApi':
    """
    Validates the model by initializing and validating an LlmApi instance.
    Args:
        model: Model object to validate.
    Returns:
        LlmApi instance.
    Raises:
        ValueError: If the model is invalid.
    """
    llm = LlmApi(model)
    llm.validate()
    return llm

def extract_summary(responses: List[str]) -> Dict[str, Any] | None:
    """
    Extracts summary information from the evaluation responses.
    Args:
        responses: List of response strings. Each response is expected to be a JSON string
            with keys 'correct_count', 'total_time', and 'total_questions'.
    Returns:
        Dictionary with grade and time, or None if not found.
    """
    for r in reversed(responses):
        try:
            data = json.loads(r.replace('data: ', '').strip())
            if {'correct_count', 'total_time', 'total_questions'}.issubset(data):
                
                normalized_score = round(data['correct_count'] / data['total_questions'] * 10, 2)
                return {
                    'grade': f"{normalized_score} ({data['correct_count']}/{data['total_questions']})",
                    'time': data['total_time']
                }
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to decode JSON in extract_summary: {e}")
            continue
    return None

def batch_stream(exams_to_eval: Iterable, models_to_eval: Iterable, repetitions: int, user_prompt: str, notes: str = None) -> Generator[str, None, None]:
    """
    Streams batch evaluation results for all combinations of exams, models, and repetitions.
    Args:
        exams_to_eval: Iterable of Exam objects to evaluate.
        models_to_eval: Iterable of Model objects to evaluate.
        repetitions: Number of repetitions for each combination.
        user_prompt: User-provided prompt to use for all evaluations.
        notes: Optional notes for all evaluations in the batch.
    Yields:
        String chunks for streaming HTTP response.
    """
    total_tasks = len(exams_to_eval) * len(models_to_eval) * repetitions
    eval_count = 0

    for exam, model, rep in generate_eval_tasks(exams_to_eval, models_to_eval, repetitions):
        try:
            questions = validate_exam(exam)
        except ValueError as e:
            logging.warning(str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            continue

        try:
            llm = validate_model(model)
        except ValueError as e:
            error_msg = f"Model {model}: {str(e)}"
            logging.warning(error_msg)
            yield f"data: {json.dumps({'error': error_msg})}\n\n"
            continue

        try:
            eval_count += 1
            subject_name = getattr(exam.course, 'name', '')
            progress_msg = (
                f"Eval {eval_count}/{total_tasks} - "
                f"Model: <b>{model.description}</b> Subject: <b>{subject_name}</b> "
                f"Exam: <b>{exam.description}</b> Repetition: {rep}/{repetitions}"
            )
            logging.info(f"Progress: {progress_msg}")
            yield f"data: {json.dumps({'progress': progress_msg})}\n\n"

            responses = []
            for chunk in stream_responses(questions, user_prompt, llm, len(questions), exam, notes):
                responses.append(chunk)
                logging.info(f"Yielding chunk: {chunk[:100]}")
                yield chunk

            summary = extract_summary(responses)
            if summary:
                yield f"data: {json.dumps({'eval_result': summary})}\n\n"
        except Exception as e:
            error_msg = f"Error during {progress_msg}: {str(e)}"
            logging.warning(error_msg)
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

    yield f"data: {json.dumps({'done': True})}\n\n"

def handle_batch_evaluations_post(request, user, exams, models):
    """
    Handles the POST logic for batch evaluations: parses request, filters objects, and returns StreamingHttpResponse.
    Args:
        request: Django HttpRequest object (POST).
        user: The current user.
        exams: Queryset of all exams for the user.
        models: Queryset of all models.
    Returns:
        StreamingHttpResponse for the batch evaluation stream.
    """
    logging.warning('Batch evaluation POST received')
    if request.content_type == 'application/json':
        data = json.loads(request.body)
        selected_exam_ids = data.get('exams[]', [])
        selected_model_ids = data.get('models[]', [])
        repetitions = int(data.get('repetitions', 1))
        user_prompt = data.get('user_prompt', '')
        notes = data.get('notes', '')
    else:
        selected_exam_ids = request.POST.getlist('exams[]')
        selected_model_ids = request.POST.getlist('models[]')
        repetitions = int(request.POST.get('repetitions', 1))
        user_prompt = request.POST.get('user_prompt', '')
        notes = request.POST.get('notes', '')

    logging.warning(f'selected_exam_ids: {selected_exam_ids}, selected_model_ids: {selected_model_ids}, repetitions: {repetitions}, user_prompt: {user_prompt}, notes: {notes}')

    exams_to_eval = exams.filter(id__in=selected_exam_ids)
    models_to_eval = [m for m in models if str(m.id) in selected_model_ids]
    logging.warning(f'exams_to_eval: {[e.id for e in exams_to_eval]}, models_to_eval: {[m.id for m in models_to_eval]}')

    return StreamingHttpResponse(
        batch_stream(exams_to_eval, models_to_eval, repetitions, user_prompt, notes),
        content_type="text/event-stream"
    )

@login_required
@csrf_exempt
def batch_evaluations_view(request):
    """
    Django view for handling batch evaluations. Supports GET for rendering the form
    and POST for streaming evaluation results.
    Args:
        request: Django HttpRequest object.
    Returns:
        HttpResponse or StreamingHttpResponse.
    """
    user = request.user
    exams = Exam.objects.filter(user=user)
    exams = exams.annotate(eval_count=Count('evaluation', filter=Q(evaluation__exam__user=user)))
    courses = Course.objects.filter(user=user)

 
    local_models, external_models = get_models_for_user(user)

    # Annotate models with evaluation count, but only count evaluations by the current user
    local_models = local_models.annotate(eval_count=Count('evaluation', filter=Q(evaluation__exam__user=user)))
    external_models = external_models.annotate(eval_count=Count('evaluation', filter=Q(evaluation__exam__user=user)))

    # Group exams by course
    courses_with_exams = {}
    for course in courses:
        exams_for_course = exams.filter(course=course)
        if exams_for_course.exists():
            courses_with_exams[course] = exams_for_course

    if request.method == 'POST':
        models = list(local_models) + list(external_models)
        return handle_batch_evaluations_post(request, user, exams, models)

    return render(request, 'batch_evaluations.html', {
        'local_models': local_models,
        'external_models': external_models,
        'subjects_with_exams': courses_with_exams,  
    })

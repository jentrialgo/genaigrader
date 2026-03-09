from django.http import StreamingHttpResponse, HttpResponse
from django.db import transaction
from genaigrader.models import Question, QuestionOption
from genaigrader.services.file_service import save_uploaded_file
from genaigrader.services.exam_service import process_exam_file, create_exam
from genaigrader.services.course_service import get_or_create_course
from genaigrader.services.model_service import get_or_create_model
from genaigrader.services.stream_service import stream_responses
from genaigrader.llm_api import LlmApi
from genaigrader.models import Exam,Evaluation,Question

def validate_model(request):
    """Retrieve and validate LLM model from the request."""
    model = get_or_create_model(request)
    llm = LlmApi(model)
    llm.validate()
    return llm


def parse_and_validate_file(uploaded_file):
    """Save the incoming file, parse exam content, and validate formatting."""
    path = save_uploaded_file(uploaded_file)
    questions_data = process_exam_file(path)
    return questions_data


def persist_exam_and_questions(uploaded_file, course, user, request, questions_data):
    """Atomically create an Exam and its Questions and Options in the database."""
    with transaction.atomic():
        exam = create_exam(uploaded_file, course, user, request)
        exam.save()

        for q_data in questions_data:
            if len(q_data['options']) < 2:
                raise ValueError(
                    f"Question '{q_data['statement'][:30]}...' has less than 2 options"
                )

            question = Question.objects.create(
                statement=q_data['statement'],
                exam=exam
            )

            correct_option = None
            for opt_content in q_data['options']:
                option = QuestionOption.objects.create(
                    content=opt_content,
                    question=question
                )
                letter = opt_content.split(')')[0].strip().lower()
                if letter == q_data['correct_option']:
                    correct_option = option

            if not correct_option:
                raise ValueError(
                    f"Question '{q_data['statement'][:30]}...' has no valid correct option"
                )

            question.correct_option = correct_option
            question.save()

    return exam


def handle_file_upload(request):
    """Main entrypoint to process an upload_file view POST request."""
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)
    try:
        # Step 1: initial validations
        course = get_or_create_course(request)
        uploaded_file = request.FILES['file']
        user = request.user

        # Step 2: model validation
        llm = validate_model(request)

        if is_unique_exam(uploaded_file,course,user,llm): #TODO Decide if we dont to allow the revaluation of the same exam or we just show a warning
            # Step 3: file parsing and validation
            questions_data = parse_and_validate_file(uploaded_file)

            # Step 4: persist to DB
            exam = persist_exam_and_questions(
                uploaded_file, course, request.user, request, questions_data
            )

            # Step 5: stream LLM response
            user_prompt = request.POST.get('user_prompt', '')
            notes = request.POST.get('notes', '')
            stream = stream_responses(
                Question.objects.filter(exam=exam),
                user_prompt,
                llm,
                len(questions_data),
                exam,
                notes
            )
            return StreamingHttpResponse(stream, content_type='text/event-stream')
        else:
            return HttpResponse(f"Error: An exam with the name '{uploaded_file.name}' already exists in this course.",status=409)

    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=400)


def is_unique_exam(file,course,user,model):
    """Searches if there´s another instance in the BD of the exam, evaluated by the same model in the same course, so there´s no duplicated exams in the database."""
    exam = Exam.objects.filter(
        description=file.name,
        course=course,
        user=user
    ).first()

    # Si el examen no existe en la base de datos, es único por definición
    if not exam:
        return True

    # Si el examen existe, comprobamos si ya hay una evaluación con ese modelo
    already_evaluated = Evaluation.objects.filter(
        exam=exam,
        model=model.model_obj
    ).exists()

    # Si NO ha sido evaluado, devolvemos True (es único/permite reevaluar)
    return not already_evaluated
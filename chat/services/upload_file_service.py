from django.http import StreamingHttpResponse, HttpResponse
from django.db import transaction
from chat.models import Question, QuestionOption
from chat.services.file_service import save_uploaded_file
from chat.services.exam_service import process_exam_file, create_exam
from chat.services.course_service import get_or_create_course
from chat.services.model_service import get_or_create_model
from chat.services.stream_service import stream_responses
from chat.llm_api import LlmApi


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

        # Step 2: model validation
        llm = validate_model(request)

        # Step 3: file parsing and validation
        questions_data = parse_and_validate_file(uploaded_file)

        # Step 4: persist to DB
        exam = persist_exam_and_questions(
            uploaded_file, course, request.user, request, questions_data
        )

        # Step 5: stream LLM response
        user_prompt = request.POST.get('user_prompt', '')
        stream = stream_responses(
            Question.objects.filter(exam=exam),
            user_prompt,
            llm,
            len(questions_data),
            exam
        )
        return StreamingHttpResponse(stream, content_type='text/event-stream')

    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=400)

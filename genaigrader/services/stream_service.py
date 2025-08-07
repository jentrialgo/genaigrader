import json
import logging
import time
from django.db import transaction
from django.utils import timezone
from genaigrader.models import Evaluation, QuestionEvaluation
from genaigrader.services.llm_service import generate_prompt
from genaigrader.services.ollama_version_service import get_evaluation_ollama_version

# Set logging level to INFO
logging.basicConfig(level=logging.INFO)

def stream_responses(questions, user_prompt, llm, total_questions, exam):
    """
    Streams evaluation results for each question, yielding JSON-encoded progress updates.

    Parameters:
    - questions: List of Question objects to be evaluated.
    - user_prompt: Custom instruction provided by the user.
    - llm: An instance of LlmApi, encapsulating model configuration and interaction.
    - total_questions: Total number of questions to evaluate.
    - exam: The Exam object associated with this evaluation.

    Yields:
    - str: Server-sent event JSON containing progress and evaluation details.
    """
    correct_count = 0
    total_evaluation_time = 0.0
    question_evaluations = []  # Store question evaluations temporarily

    evaluation = Evaluation(
        prompt=(
            user_prompt +
            " Te voy a pasar una pregunta de test y tienes que responderme con qué opción es la correcta. "
            "Sólo debes decirme la opción, por ejemplo 'a', absolutamente nada más.\n"
        ),
        ev_date=timezone.now(),
        grade=0,
        model=llm.model_obj, 
        exam=exam,
        time=0.0,
        ollama_version=get_evaluation_ollama_version(llm.model_obj)
    )

    for index, question in enumerate(questions):
        start_time = time.monotonic()

        try:
            progress = process_question(
                correct_count,
                index,
                question,
                user_prompt,
                llm,
                total_questions,
                evaluation,
                question_evaluations
            )
        except Exception as e:
            logging.error(f"Error processing question {index + 1}: {e}")
            error_json = {
                "error": str(e),
                "processed_questions": index + 1,
                "total_questions": total_questions,
                "correct_count": correct_count
            }
            yield f"data: {json.dumps(error_json)}\n\n"
            return # Terminate the evaluation if an error occurs

        end_time = time.monotonic()
        question_time = end_time - start_time
        total_evaluation_time += question_time

        correct_count = progress['correct_count']
        progress['time'] = round(question_time, 2)

        if index == len(questions) - 1:
            progress['total_time'] = round(total_evaluation_time, 2)

        yield f"data: {json.dumps(progress)}\n\n"

    # All questions processed successfully, now save everything in a transaction
    with transaction.atomic():
        evaluation.grade = round((correct_count / total_questions * 10), 2) if total_questions > 0 else 0.0
        evaluation.time = round(total_evaluation_time, 2)
        evaluation.save()

        for q_eval in question_evaluations:
            q_eval.evaluation = evaluation
            q_eval.save()

def process_question(correct_count, index, question, user_prompt, llm, total_questions, evaluation, question_evaluations):
    """
    Processes a single question using the provided LlmApi instance and updates evaluation state.

    Parameters:
    - correct_count: Number of correct answers so far.
    - index: Index of the current question.
    - question: The Question object to be evaluated.
    - user_prompt: Instructional prefix to influence model behavior.
    - llm: An instance of LlmApi to generate the model response.
    - total_questions: Total number of questions in the session.
    - evaluation: The Evaluation database object to associate with results.
    - question_evaluations: List to store question evaluations temporarily.

    Returns:
    - dict: A dictionary containing processed question data and result.
    """
    prompt_data = generate_prompt(question, user_prompt)
    logging.info(f"Question prompt: {prompt_data['prompt']}")
    llm_response_list = list(llm.generate_response(prompt_data['prompt']))
    logging.info(f"LLM response: {''.join(llm_response_list)}\n")

    if not llm_response_list:
        # An example of a case where the LLM doesn't return any response
        # is qwen3.06b: it get's stuck in an infinite loop in the thiking
        # phase and, in the end, it doesn't generate the "</thinking>" tag
        # and, therefore, it doesn't return any response.
        response = ""
    else:
        response = llm_response_list[0].strip().lower()[0]

    is_correct = (response == question.correct_option.content.strip().lower()[0])

    question_eval = QuestionEvaluation(
        question=question,
        question_option=question.correct_option
    )
    question_evaluations.append(question_eval)

    if is_correct:
        correct_count += 1

    return {
        "processed_questions": index + 1,
        "total_questions": total_questions,
        "correct_count": correct_count,
        "response": {
            "question_prompt": prompt_data['question_prompt'],
            "user_prompt": prompt_data['user_prompt'],
            "prompt": prompt_data['prompt'],
            "response": response,
            "correct_option": question.correct_option.content,
            "is_correct": is_correct,
        }
    }
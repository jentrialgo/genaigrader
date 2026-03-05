from django.http import HttpResponse
from genaigrader.models import Question, Evaluation, QuestionEvaluation


def calculate_question_analytics(question):
    """
    Calculates analytics for a given question based on its evaluations.

    Parameters:
    - question: Question instance for which to calculate analytics.

    Returns:
    - dict containing total evaluations, correct evaluations, and accuracy.
    """
    #Get all evaluations for the question
    question_evaluations = QuestionEvaluation.objects.filter(
        question_id=question.id
    ).select_related('evaluation__model', 'question_option')

    models_data = {}

    #foreach evaluation, check if the answer is correct and aggregate data by model
    for question_evaluation in question_evaluations:
        model = question_evaluation.evaluation.model
        model_key = model.id

        if model_key not in models_data:
            models_data[model_key] = {
                'model_id': model.id,
                'model_name': model.description,
                'correct': 0,
                'total': 0,
                'times': []
            }

        # Check if answer is correct
        is_correct = question_evaluation.question_option_id == question.correct_option
        models_data[model_key]['correct'] += int(is_correct)
        models_data[model_key]['total'] += 1
        models_data[model_key]['times'].append(question.evaluation.time)
    results = []

    # Calculate accuracy and average time for each model, using the data obtained before
    for model_data in models_data.values():
        accuracy = (model_data['correct'] / model_data['total'] * 100) if model_data['total'] > 0 else 0
        avg_time = sum(model_data['times']) / len(model_data['times']) if model_data['times'] else 0

        results.append({
            'model_id': model_data['model_id'],
            'model_name': model_data['model_name'],
            'accuracy': round(accuracy, 2),
            'avg_time': round(avg_time, 2),
            'total_evaluations': model_data['total']
        })

    return HttpResponse(results)

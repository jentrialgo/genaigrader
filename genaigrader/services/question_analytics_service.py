from genaigrader.models import QuestionEvaluation


def calculate_question_analytics(question):
    """
    Calculates analytics for a given question based on its evaluations.

    Parameters:
    - question: Question instance for which to calculate analytics.

    Returns:
    - list of dict with per-model totals and accuracy.
    """
    # Fetch all evaluations for this question with required relations.
    question_evaluations = QuestionEvaluation.objects.filter(
        question_id=question.id
    ).select_related('evaluation__model', 'question_option')

    models_data = {}

    # Aggregate correctness totals grouped by model.
    for question_evaluation in question_evaluations:
        model = question_evaluation.evaluation.model
        model_key = model.id

        if model_key not in models_data:
            models_data[model_key] = {
                'model_id': model.id,
                'model_name': model.description,
                'correct': 0,
                'invalid': 0,
                'total': 0
            }

        selected_option_id = question_evaluation.question_option_id
        is_invalid = selected_option_id is None

        if is_invalid:
            models_data[model_key]['invalid'] += 1

        is_correct = (
            selected_option_id is not None and
            question.correct_option_id is not None and
            selected_option_id == question.correct_option_id
        )

        models_data[model_key]['correct'] += int(is_correct)
        models_data[model_key]['total'] += 1

    results = []
    # Build the final per-model analytics payload.
    for model_data in models_data.values():
        accuracy = (model_data['correct'] / model_data['total'] * 100) if model_data['total'] > 0 else 0

        results.append({
            'model_id': model_data['model_id'],
            'model_name': model_data['model_name'],
            'accuracy': round(accuracy, 2),
            'total_evaluations': model_data['total'],
            'invalid_evaluations': model_data['invalid']
        })

    return results

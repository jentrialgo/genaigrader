from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from genaigrader.models import Exam, Evaluation, Question
from django.views.decorators.http import require_http_methods
from genaigrader.services.graphics_service import process_evaluations_for_graphics, compute_model_statistics
from genaigrader.services.question_analytics_service import calculate_question_analytics
@login_required
def exam_detail(request, exam_id):
    exam = get_object_or_404(
        Exam.objects.select_related('course', 'user')
                    .prefetch_related(
                        'question_set__questionoption_set',
                        'question_set__correct_option',
                        'evaluation_set__model'
                    ),
        id=exam_id,
        course__user=request.user
    )
    
    evaluations = exam.evaluation_set.all()
    model_values = process_evaluations_for_graphics(evaluations)
    model_averages, time_averages = compute_model_statistics(model_values)
    
    return render(request, 'exam_detail.html', {
        'exam': exam,
        'course': exam.course,
        'questions': exam.question_set.all(),
        'evaluations': evaluations,
        'model_averages': model_averages,
        'time_averages': time_averages
    })

@login_required
@require_http_methods(["DELETE"])
def delete_evaluation(request, eval_id):
    try:
        evaluation = get_object_or_404(
            Evaluation.objects.select_related('exam__course'),
            id=eval_id,
            exam__course__user=request.user
        )
        evaluation.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def question_analytics(request, question_id):
    try:
        question = Question.objects.get(id=question_id)
        stats = calculate_question_analytics(question)
        return JsonResponse({'success': True, 'data': stats})
    except Question.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Question not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
import csv

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from genaigrader.models import Course, Evaluation, Exam
from genaigrader.services.course_service import create_new_course


@login_required
def course_view(request):
    if request.method == "POST":
        try:
            course_name = request.POST.get("course_name")
            new_course = create_new_course(name=course_name, user=request.user)
            return JsonResponse(
                {
                    "status": "success",
                    "course": {"id": new_course.id, "name": new_course.name},
                }
            )
        except ValidationError as e:
            return JsonResponse({"status": "error", "message": e.message}, status=400)
    courses = Course.objects.filter(user=request.user).prefetch_related("exam_set")
    return render(request, "course.html", {"courses": courses})


@login_required
@require_http_methods(["PUT"])
def update_course(request, course_id):
    try:
        course = Course.objects.get(id=course_id, user=request.user)
        data = QueryDict(request.body)
        course.name = data.get("name")
        course.save()
        return JsonResponse({"status": "success"})
    except Course.DoesNotExist:
        return JsonResponse({"status": "error"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_course(request, course_id):
    try:
        course = Course.objects.get(id=course_id, user=request.user)
        course.delete()
        return JsonResponse({"status": "success"})
    except Course.DoesNotExist:
        return JsonResponse({"status": "error"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_http_methods(["PUT"])
def update_exam(request, exam_id):
    try:
        exam = Exam.objects.select_related("course").get(
            id=exam_id, course__user=request.user
        )
        data = QueryDict(request.body)
        exam.description = data.get("description")
        exam.save()
        return JsonResponse({"status": "success"})
    except Exam.DoesNotExist:
        return JsonResponse({"status": "error"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_exam(request, exam_id):
    try:
        exam = Exam.objects.select_related("course").get(
            id=exam_id, course__user=request.user
        )
        exam.delete()
        return JsonResponse({"status": "success"})
    except Exam.DoesNotExist:
        return JsonResponse({"status": "error"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
def export_all_evaluations(request):
    # Set response
    response = HttpResponse(
        content_type="text/csv; charset=utf-8-sig"
    )  # Encoding for Excel
    response["Content-Disposition"] = 'attachment; filename="all_evaluations.csv"'

    # Create CSV writer
    writer = csv.writer(response, delimiter=",", quoting=csv.QUOTE_ALL)

    # Write header
    writer.writerow(["Course", "Exam", "Date", "Model", "Prompt", "Grade", "Time (s)"])

    # Get evaluations with related data
    evaluations = (
        Evaluation.objects.filter(exam__course__user=request.user)
        .select_related("exam__course", "model")
        .order_by("exam__course__name", "exam__description")
    )

    # Write rows
    for eval in evaluations:
        writer.writerow(
            [
                eval.exam.course.name,
                eval.exam.description,
                eval.ev_date.strftime("%d/%m/%Y %H:%M:%S"),
                eval.model.description,
                eval.prompt,
                str(eval.grade).replace(".", ","),
                str(round(eval.time, 2)).replace(".", ","),
            ]
        )

    return response


@login_required
def export_course_evaluations(request, course_id):
    # Verify course
    course = get_object_or_404(Course, id=course_id, user=request.user)

    # Set response
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = (
        f'attachment; filename="evaluations_{course.name}.csv"'
    )

    # Create writer
    writer = csv.writer(response, delimiter=",", quoting=csv.QUOTE_ALL)

    # Write header
    writer.writerow(["Exam", "Date", "Model", "Prompt", "Grade", "Time (s)"])

    # Get evaluations
    evaluations = Evaluation.objects.filter(exam__course=course).select_related(
        "exam", "model"
    )

    # Write rows
    for eval in evaluations:
        writer.writerow(
            [
                eval.exam.description,
                eval.ev_date.strftime("%d/%m/%Y %H:%M:%S"),
                eval.model.description,
                eval.prompt,
                str(eval.grade).replace(".", ","),
                str(round(eval.time, 2)).replace(".", ","),
            ]
        )

    return response

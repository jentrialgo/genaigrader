import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods
from django_q.tasks import async_task

from genaigrader.models import Model
from genaigrader.services.get_models_service import get_models_for_user
from genaigrader.services.model_service import DEFAULT_MODEL_COLOR
from genaigrader.tasks import download_model_task


@login_required
def api_view(request):
    local_models, external_models = get_models_for_user(request.user)
    return render(
        request,
        "api.html",
        {
            "local_models": local_models,
            "external_models": external_models,
            "default_model_color": DEFAULT_MODEL_COLOR,
        },
    )


@login_required
@require_http_methods(["PUT"])
def update_model(request, model_id):
    try:
        model = get_object_or_404(Model, id=model_id)
        if model.user != request.user and not request.user.is_superuser:
            return JsonResponse(
                {"status": "error", "message": "Forbidden"},
                status=403,
            )
        data = QueryDict(request.body)
        model.description = data.get("description", model.description)
        model.api_url = data.get("api_url", model.api_url)
        model.api_key = data.get("api_key", model.api_key)
        model.save()
        return JsonResponse({"status": "success"})
    except (ValueError, TypeError, ValidationError) as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_model(request, model_id):
    try:
        model = get_object_or_404(Model, id=model_id)

        if not request.user.is_superuser and model.user != request.user:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Permission denied. Only owners or superusers can delete models.",
                },
                status=403,
            )
        model.delete()
        return JsonResponse({"status": "success"})
    except (ValueError, TypeError, ValidationError) as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def create_model(request):
    try:
        data = QueryDict(request.body)
        new_model = Model.objects.create(
            description=data["description"],
            api_url=data["api_url"],
            api_key=data["api_key"],
            user=request.user,
        )
        return JsonResponse(
            {
                "status": "success",
                "model": {
                    "id": new_model.id,
                    "description": new_model.description,
                    "api_url": new_model.api_url,
                },
            }
        )
    except KeyError as e:
        return JsonResponse(
            {"status": "error", "message": f"Missing field: {e}"},
            status=400,
        )
    except (ValueError, TypeError, ValidationError) as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def pull_model(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON body"},
            status=400,
        )

    model_name = data.get("model", "").strip()

    if not model_name:
        return JsonResponse(
            {"status": "error", "message": "Model name cannot be empty."},
            status=400,
        )

    if Model.objects.filter(description=model_name).exists():
        return JsonResponse(
            {
                "status": "error",
                "message": f'Model "{model_name}" already exists in the database.',
            },
            status=400,
        )

    try:
        task_id = async_task(download_model_task, model_name, timeout=7200)
    except (ValueError, TypeError) as e:
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=400,
        )

    return JsonResponse(
        {
            "status": "queued",
            "task_id": task_id,
            "message": f"Model {model_name} queued for download",
        }
    )

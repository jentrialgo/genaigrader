import json

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse, QueryDict, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from genaigrader.llm_api import is_private_url
from genaigrader.models import Model
from genaigrader.services.get_models_service import get_models_for_user
from genaigrader.services.model_service import DEFAULT_MODEL_COLOR

OLLAMA_BASE_URL = settings.OLLAMA_API_URL


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
    model = Model.objects.filter(id=model_id).first()
    if model is None:
        return JsonResponse(
            {"status": "error", "message": "Model not found"}, status=404
        )

    if (
        model.is_external
        and model.user_id != request.user.id
        and not request.user.is_superuser
    ):
        return JsonResponse(
            {"status": "error", "message": "Permission denied."},
            status=403,
        )
    if not model.is_external and not request.user.is_superuser:
        return JsonResponse(
            {
                "status": "error",
                "message": "Only superusers can modify local models.",
            },
            status=403,
        )

    try:
        data = QueryDict(request.body)
        new_url = data.get("api_url")
        if new_url and is_private_url(new_url):
            return JsonResponse(
                {
                    "status": "error",
                    "message": "API URL resolves to a private or reserved IP address.",
                },
                status=400,
            )

        if "description" in data:
            model.description = data["description"]
        if new_url is not None:
            model.api_url = new_url
        if "api_key" in data:
            model.api_key = data["api_key"]
        model.save()
        return JsonResponse({"status": "success"})
    except (ValueError, TypeError, ValidationError) as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_model(request, model_id):
    model = Model.objects.filter(id=model_id).first()
    if model is None:
        return JsonResponse(
            {"status": "error", "message": "Model not found"}, status=404
        )

    if model.is_external:
        if model.user_id != request.user.id and not request.user.is_superuser:
            return JsonResponse(
                {"status": "error", "message": "Permission denied."},
                status=403,
            )
    else:
        if not request.user.is_superuser:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Permission denied. Only superusers can delete local models.",
                },
                status=403,
            )

    model.delete()
    return JsonResponse({"status": "success"})


@login_required
@require_http_methods(["POST"])
def create_model(request):
    try:
        data = QueryDict(request.body)
        new_url = data.get("api_url")
        if new_url and is_private_url(new_url):
            return JsonResponse(
                {
                    "status": "error",
                    "message": "API URL resolves to a private or reserved IP address.",
                },
                status=400,
            )

        new_model = Model.objects.create(
            description=data["description"],
            api_url=new_url,
            api_key=data.get("api_key"),
            user=request.user,
        )
        return JsonResponse(
            {
                "status": "success",
                "model": {
                    "id": new_model.id,
                    "description": new_model.description,
                    "api_url": new_model.api_url,
                    "api_key": new_model.api_key,
                },
            }
        )
    except (ValueError, TypeError, ValidationError) as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def pull_model(request):
    if not request.user.is_superuser:
        return JsonResponse(
            {
                "status": "error",
                "message": "Only superusers can pull local models.",
            },
            status=403,
        )

    try:
        data = json.loads(request.body)
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

        ollama_url = f"{OLLAMA_BASE_URL}/api/pull"

        response = requests.post(ollama_url, json={"name": model_name}, stream=True)

        if response.status_code != 200:
            return JsonResponse(
                {"status": "error", "message": f"Ollama error: {response.text}"},
                status=400,
            )

        def stream_generator():
            download_complete = False
            error_occurred = False

            for line in response.iter_lines():
                if line:
                    try:
                        ollama_chunk = json.loads(line)

                        if "status" in ollama_chunk:
                            yield json.dumps(
                                {
                                    "status": "progress",
                                    "message": f'Downloading: {ollama_chunk["status"]}',
                                }
                            ) + "\n"

                        if "error" in ollama_chunk:
                            yield json.dumps(
                                {
                                    "status": "error",
                                    "message": f'Error: {ollama_chunk["error"]}',
                                }
                            ) + "\n"
                            error_occurred = True
                            break

                        if ollama_chunk.get("status") == "success":
                            download_complete = True

                    except json.JSONDecodeError:
                        yield json.dumps(
                            {
                                "status": "error",
                                "message": "Error reading Ollama response",
                            }
                        ) + "\n"
                        error_occurred = True
                        break

            if download_complete and not error_occurred:
                try:
                    new_model = Model.objects.create(
                        description=model_name,
                    )
                    yield json.dumps(
                        {
                            "status": "success",
                            "message": f"Model {model_name} downloaded successfully!",
                            "model_id": new_model.id,
                        }
                    ) + "\n"
                except (ValueError, TypeError) as e:
                    yield json.dumps(
                        {
                            "status": "error",
                            "message": f"Error creating model: {str(e)}",
                        }
                    ) + "\n"

        return StreamingHttpResponse(
            stream_generator(), content_type="application/json"
        )

    except requests.RequestException:
        return JsonResponse(
            {
                "status": "error",
                "message": "Could not connect to Ollama. Is it running?",
            },
            status=500,
        )
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=400,
        )

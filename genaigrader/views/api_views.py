import json

import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, QueryDict, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from genaigrader.models import Model
from genaigrader.services.get_models_service import get_models_for_user

OLLAMA_BASE_URL = "http://localhost:11434"


@login_required
def api_view(request):
    local_models, external_models = get_models_for_user(request.user)
    return render(
        request,
        "api.html",
        {"local_models": local_models, "external_models": external_models},
    )


@require_http_methods(["PUT"])
def update_model(request, model_id):
    try:
        model = get_object_or_404(Model, id=model_id)
        data = QueryDict(request.body)
        model.description = data.get("description")
        model.api_url = data.get("api_url")
        model.api_key = data.get("api_key")
        model.save()
        return JsonResponse({"status": "success"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@require_http_methods(["DELETE"])
def delete_model(request, model_id):
    try:
        model = get_object_or_404(Model, id=model_id)

        if not model.is_external and not request.user.is_superuser:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Permission denied. Only superusers can delete models.",
                },
                status=403,
            )
        model.delete()
        return JsonResponse({"status": "success"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


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
                    "api_key": new_model.api_key,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@csrf_exempt
def pull_model(request):
    if request.method == "POST":
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

            # Make the request to Ollama with streaming
            response = requests.post(ollama_url, json={"name": model_name}, stream=True)

            # Handle connection errors with Ollama
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

                            # Send progress to client
                            if "status" in ollama_chunk:
                                yield json.dumps(
                                    {
                                        "status": "progress",
                                        "message": f'Downloading: {ollama_chunk["status"]}',
                                    }
                                ) + "\n"

                            # Detect errors
                            if "error" in ollama_chunk:
                                yield json.dumps(
                                    {
                                        "status": "error",
                                        "message": f'Error: {ollama_chunk["error"]}',
                                    }
                                ) + "\n"
                                error_occurred = True
                                break

                            # Detect successful completion
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

                # Create model only if download was successful
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
                    except Exception as e:
                        yield json.dumps(
                            {
                                "status": "error",
                                "message": f"Error creating model: {str(e)}",
                            }
                        ) + "\n"

            return StreamingHttpResponse(
                stream_generator(), content_type="application/json"
            )

        except requests.exceptions.ConnectionError:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Could not connect to Ollama. Is it running?",
                },
                status=500,
            )
        except Exception as e:
            return JsonResponse(
                {"status": "error", "message": f"Unexpected error: {str(e)}"},
                status=500,
            )

    return JsonResponse(
        {"status": "error", "message": "Method not allowed"}, status=405
    )

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from genaigrader.models import Course
from genaigrader.services.get_models_service import get_models_for_user
from genaigrader.services.upload_file_service import handle_file_upload


@login_required
def evaluate_view(request):
    """Render the exam page with models and courses"""
    local_models, external_models = get_models_for_user(request.user)
    courses = Course.objects.filter(user=request.user)
    return render(
        request,
        "evaluate.html",
        {
            "courses": courses,
            "local_models": local_models,
            "external_models": external_models,
        },
    )


@csrf_exempt
def upload_file(request):
    """Handle exam upload and processing with full validation"""
    return handle_file_upload(request)

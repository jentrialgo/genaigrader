from genaigrader.models import Model


def get_or_create_model(request):
    model = request.POST.get("model", "llama3.2:1b")
    model_name = model or "llama3.2:1b"
    model, created = Model.objects.get_or_create(description=model_name)
    return model

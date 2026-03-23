from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = user.username
            messages.success(
                request, f"¡Cuenta creada para {username}! Ahora puedes iniciar sesión."
            )
            return redirect("login")
        else:
            messages.error(
                request, "Hubo un error en el formulario. Corrige los campos."
            )
    else:
        form = UserCreationForm()

    return render(request, "registration/signup.html", {"form": form})

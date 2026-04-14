from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from genaigrader.forms import UserSettingsForm
from users.models import CustomUser


class UserSettingsView(LoginRequiredMixin, UpdateView):
    model = CustomUser

    form_class = UserSettingsForm
    template_name = "account/profile_settings.html"
    success_url = reverse_lazy("user_settings")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        email_changed = "email" in form.changed_data
        response = super().form_valid(form)

        if email_changed:
            user = self.object
            new_email = user.email

            EmailAddress.objects.filter(user=user).delete()

            email_record = EmailAddress.objects.create(
                user=user, email=new_email, primary=True, verified=False
            )

            email_record.send_confirmation(self.request)

            messages.success(
                self.request,
                "Email updated. We have sent a verification link to your new address.",
            )
        else:
            messages.success(self.request, "Profile updated successfully.")

        return response

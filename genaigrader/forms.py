from django import forms

from users.models import CustomUser


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["username", "first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Username is immutable for all users.
        self.fields["username"].disabled = True
        self.fields["username"].widget.attrs["readonly"] = True

        current_email = (self.instance.email or "").strip().lower()
        if not current_email.endswith("@genaigrader.local"):
            # Non-legacy users cannot change email.
            self.fields["email"].disabled = True
            self.fields["email"].widget.attrs["readonly"] = True

    def clean_username(self):
        # Extra backend safeguard against mutation attempts.
        return self.instance.username

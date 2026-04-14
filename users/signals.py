from allauth.socialaccount.signals import pre_social_login
from django.contrib.auth.signals import user_logged_in
from django.contrib.messages import warning
from django.dispatch import receiver

from users.adapters import sync_external_identity


@receiver(pre_social_login)
def sync_external_identity_on_prelogin(sender, request, sociallogin, **kwargs):
    account = getattr(sociallogin, "account", None)
    if account is None:
        return
    if getattr(account, "user_id", None) is None:
        return
    sync_external_identity(account)


@receiver(user_logged_in)
def warn_temporary_email(sender, request, user, **kwargs):
    if user.email and user.email.endswith("@genaigrader.local"):
        warning(
            request,
            "Your account is using a system-generated email address. "
            "Please go to your profile and update it to a real email so you do not lose access.",
        )

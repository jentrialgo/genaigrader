from __future__ import annotations

import re
from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.messages import constants as message_constants
from django.core.exceptions import ValidationError
from django.shortcuts import redirect

from users.models import ExternalIdentity


def _normalize_username_seed(value: str) -> str:
    seed = re.sub(r"[^a-z0-9._-]", "", (value or "").strip().lower())
    return seed or "user"


def _build_unique_username(seed: str, user_pk: Any = None) -> str:
    user_model = get_user_model()
    base = _normalize_username_seed(seed)
    candidate = base[:150]
    suffix = 1

    queryset = user_model.objects.all()
    if user_pk is not None:
        queryset = queryset.exclude(pk=user_pk)

    while queryset.filter(username__iexact=candidate).exists():
        token = f".{suffix}"
        candidate = f"{base[:150 - len(token)]}{token}"
        suffix += 1

    return candidate


def map_social_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()

    if normalized in {"google", "google_oauth2"}:
        return ExternalIdentity.Provider.GOOGLE
    if normalized == "upm":
        return ExternalIdentity.Provider.UPM

    return ExternalIdentity.Provider.OIDC


def sync_external_identity(account: SocialAccount) -> ExternalIdentity:
    provider = map_social_provider(account.provider)
    subject = account.uid

    identity, _ = ExternalIdentity.objects.update_or_create(
        provider=provider,
        subject=subject,
        defaults={
            "user": account.user,
            "extra_data": account.extra_data,
        },
    )
    return identity


def _add_auth_error_message(request: Any, text: str) -> None:
    if request is None:
        return
    messages.add_message(
        request,
        message_constants.ERROR,
        text,
        fail_silently=True,
    )


class AccountAdapter(DefaultAccountAdapter):
    RESERVED_USERNAMES = {
        "admin",
        "root",
        "api",
        "accounts",
        "login",
        "logout",
        "signup",
    }

    def clean_username(self, username: str, shallow: bool = False) -> str:
        clean_value = super().clean_username(username, shallow=shallow).strip()

        if clean_value.lower() in self.RESERVED_USERNAMES:
            raise ValidationError("This username is reserved.")

        user_model = get_user_model()
        username_field = user_model._meta.get_field(user_model.USERNAME_FIELD)
        for validator in username_field.validators:
            validator(clean_value)

        return clean_value

    def clean_email(self, email: str) -> str:
        normalized = (email or "").strip().lower()
        user_model = get_user_model()
        existing_users = user_model.objects.filter(email__iexact=normalized)

        request = getattr(self, "request", None)
        request_user = getattr(request, "user", None)
        if getattr(request_user, "is_authenticated", False):
            existing_users = existing_users.exclude(pk=request_user.pk)

        if existing_users.exists():
            raise ValidationError("A user with this email already exists.")
        return super().clean_email(normalized)

    def populate_username(self, request: Any, user: Any) -> None:
        if getattr(user, "username", ""):
            return

        local_part = (getattr(user, "email", "") or "").split("@", 1)[0]
        user.username = _build_unique_username(local_part, getattr(user, "pk", None))

    def is_open_for_signup(self, request: Any) -> bool:
        return (
            settings.ACCOUNT_SIGNUP_ENABLED
            if hasattr(settings, "ACCOUNT_SIGNUP_ENABLED")
            else True
        )

    def authenticate(self, request: Any, **credentials: Any) -> Any:
        user = super().authenticate(request, **credentials)
        if user is None:
            return None

        if SocialAccount.objects.filter(user=user).exists():
            _add_auth_error_message(
                request,
                "This account only allows social login.",
            )
            return None

        return user


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _get_verified_email(self, sociallogin: Any) -> str:
        for email_address in getattr(sociallogin, "email_addresses", []):
            if getattr(email_address, "verified", False):
                return (getattr(email_address, "email", "") or "").strip().lower()

        extra_data = (
            getattr(getattr(sociallogin, "account", None), "extra_data", {}) or {}
        )
        extra_email = (extra_data.get("email") or "").strip().lower()
        if extra_email and self._truthy(extra_data.get("email_verified")):
            return extra_email

        user_email = (
            (getattr(getattr(sociallogin, "user", None), "email", "") or "")
            .strip()
            .lower()
        )
        if user_email and self._truthy(extra_data.get("email_verified")):
            return user_email

        return ""

    def pre_social_login(self, request: Any, sociallogin: Any) -> None:
        request_user = getattr(request, "user", None)
        if getattr(request_user, "is_authenticated", False):
            _add_auth_error_message(
                request,
                "You cannot link another social login to an already signed-in account.",
            )
            raise ImmediateHttpResponse(redirect("account_login"))

        if sociallogin.is_existing:
            return

        verified_email = self._get_verified_email(sociallogin)
        if not verified_email:
            _add_auth_error_message(
                request,
                "This provider did not return a verified email. Access denied.",
            )
            raise ImmediateHttpResponse(redirect("account_login"))

        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=verified_email).first()
        if user is not None:
            _add_auth_error_message(
                request,
                "This email already exists with another login method.",
            )
            raise ImmediateHttpResponse(redirect("account_login"))

    def populate_user(
        self, request: Any, sociallogin: Any, data: dict[str, Any]
    ) -> Any:
        user = super().populate_user(request, sociallogin, data)

        if not getattr(user, "username", ""):
            email = (data.get("email") or "").strip().lower()
            local_part = email.split("@", 1)[0] if email else ""
            seed = (
                data.get("username")
                or data.get("preferred_username")
                or local_part
                or data.get("name")
                or sociallogin.account.uid
            )
            user.username = _build_unique_username(seed, getattr(user, "pk", None))

        return user

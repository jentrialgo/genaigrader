import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, blank=False)
    api_token = models.CharField(max_length=64, unique=True, blank=True, editable=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def save(self, *args, **kwargs):
        if not self.api_token:
            self.api_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def rotate_api_token(self):
        self.api_token = secrets.token_urlsafe(32)
        self.save(update_fields=["api_token"])

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"


class ExternalIdentity(models.Model):
    class Provider(models.TextChoices):
        OIDC = "oidc", "Generic OpenID Connect"
        UPM = "upm", "UPM"
        GOOGLE = "google", "Google Workspace"

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="external_identities"
    )
    provider = models.CharField(max_length=50, choices=Provider.choices)
    subject = models.CharField(max_length=255)
    extra_data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "External identity"
        verbose_name_plural = "External identities"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "subject"],
                name="uniq_external_identity_provider_subject",
            )
        ]

    def __str__(self):
        return f"{self.provider}:{self.subject} -> {self.user.email}"

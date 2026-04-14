from django.conf import settings


def auth_flags(_request):
    """Expose auth feature flags for template rendering decisions."""
    return {
        "GOOGLE_OAUTH_ENABLED": getattr(settings, "GOOGLE_OAUTH_ENABLED", False),
    }

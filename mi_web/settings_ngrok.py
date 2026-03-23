import os

from .settings import *

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost").split(",")

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(
    BASE_DIR, "staticfiles"
)  # where collectstatic will put static files

# Insert WhiteNoise middleware at index 1 to ensure it comes after security middleware
# and before other middleware that processes requests.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

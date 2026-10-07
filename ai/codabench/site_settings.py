"""Private headless Codabench: OJ remains the sole student-facing application."""
import os
from pathlib import Path

# Set before importing upstream: otherwise it tries to generate a .env in /app.
os.environ["SECRET_KEY"] = Path("/run/secrets/coda_secret").read_text().strip()
from .base import *  # noqa: E402,F401,F403

DEBUG = False
USE_X_FORWARDED_HOST = False
ALLOWED_HOSTS = ["codabench", "localhost", "127.0.0.1"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
ENABLE_SIGN_UP = False
ENABLE_SIGN_IN = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": "WARNING"}}

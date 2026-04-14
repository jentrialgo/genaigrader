#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main():
    """Run administrative tasks."""
    # Load .env file at the very beginning
    base_dir = Path(__file__).resolve().parent

    # Use .env.test for local tests (no DATABASE_URL), otherwise use .env
    if "test" in sys.argv:
        env_file = base_dir / ".env.test"
    else:
        env_file = base_dir / ".env"

    if env_file.exists():
        load_dotenv(env_file)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mi_web.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

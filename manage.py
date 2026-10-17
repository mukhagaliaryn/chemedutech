#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main():
    # .env may choose the settings module (the server sets DJANGO_SETTINGS_MODULE=config.settings.prod there)
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(Path(__file__).resolve().parent / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

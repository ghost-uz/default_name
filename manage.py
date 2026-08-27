#!/usr/bin/env python
"""Dard.uz — Django boshqaruv skripti.

Standart sozlama: config.settings.dev
Boshqasini tanlash uchun:  DJANGO_SETTINGS_MODULE=config.settings.prod
"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django topilmadi. Virtual muhit faollashtirilganmi?\n"
            "  Windows:  .venv\\Scripts\\activate\n"
            "  Linux:    source .venv/bin/activate"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

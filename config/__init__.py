"""Dard.uz loyiha paketi.

Celery ilovasi shu yerda import qilinadi, chunki Django ishga tushganda
`@shared_task` dekoratori uni topa olishi kerak.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)

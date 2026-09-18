"""Email notifications for task changes and important events."""

from .emailer import Emailer
from .service import notify_important_digest, notify_task_change

__all__ = ["Emailer", "notify_task_change", "notify_important_digest"]

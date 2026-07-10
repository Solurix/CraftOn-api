"""ORM models. Importing this package registers every table on ``Base.metadata``
so Alembic autogeneration and ``create_all`` see the full schema.
"""

from app.models.app_config import AppConfig
from app.models.application import Application
from app.models.contractor_profile import ContractorProfile
from app.models.device import Device
from app.models.document import Document
from app.models.job import Job
from app.models.matching import Matching
from app.models.message import Message
from app.models.notification import Notification
from app.models.review import Review
from app.models.saved_job import SavedJob
from app.models.trade import Trade
from app.models.user import User
from app.models.worker_profile import WorkerProfile

__all__ = [
    "AppConfig",
    "Application",
    "ContractorProfile",
    "Device",
    "Document",
    "Job",
    "Matching",
    "Message",
    "Notification",
    "Review",
    "SavedJob",
    "Trade",
    "User",
    "WorkerProfile",
]

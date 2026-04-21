from django.db import models
from django.utils.translation import gettext_lazy as _


class ConversionStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")
    EXEMPT = "exempt", _("Exempt")
    NOT_APPLICABLE = "not_applicable", _("N/A")

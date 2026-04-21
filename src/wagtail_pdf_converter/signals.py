"""
Signals for PDF transformation.
"""

import logging

from typing import TYPE_CHECKING, Any

from django.db.models.signals import post_save
from django.dispatch import receiver
from wagtail.documents import get_document_model

from .conf import settings as conf_settings


logger = logging.getLogger(__name__)
Document = get_document_model()

if TYPE_CHECKING:
    from wagtail.documents.models import Document as WagtailDocument


@receiver(post_save, sender=Document)
def check_and_trigger_pdf_conversion(
    sender: type["WagtailDocument"],
    instance: "WagtailDocument",
    created: bool,
    **kwargs: Any,
) -> None:
    """
    Check if PDF conversion should be triggered for a document.

    Args:
        sender: The model class
        instance: The Document instance
        created: Whether this is a new instance
        **kwargs: Additional signal arguments
    """
    # Check if automatic conversion is enabled
    if not conf_settings.AUTO_CONVERT_PDFS:
        logger.debug(f"Auto-conversion disabled, skipping document {instance.id}")
        return

    # Only process PDF files
    if not instance.is_pdf:
        return

    # Check if the document is eligible for conversion based on the configured helper
    HelperClass = conf_settings.DOCUMENT_CONVERSION_QUERY_HELPER
    if not HelperClass.eligible_for_conversion().filter(pk=instance.pk).exists():
        logger.debug(f"Document {instance.id} is not eligible for conversion.")
        return

    if created:
        # Do nothing on document creation.
        # Because in most cases, editors will want to make changes to the title,
        # taxonomy fields, etc. after uploading a document.
        # Conversion is instead triggered after making a subsequent save of the document.
        return

    # We're importing here to ensure the task is resolved at run time,
    # not at import time. This helps with:
    #
    # 1. Testing: allows Django's `@override_settings` and Python's
    #    `@mock.patch` to work correctly. The test environment is only
    #    configured during the test's execution, long after the initial
    #    module import.
    #
    # 2. App Loading: sidesteps potential circular dependency errors
    #    that can occur during Django's startup process.
    from .tasks import trigger_conversion_if_needed

    trigger_conversion_if_needed(instance)

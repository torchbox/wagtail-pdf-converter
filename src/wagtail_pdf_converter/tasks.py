"""
Tasks for PDF to markdown conversion.
"""

import logging

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone
from django_tasks import task
from wagtail.documents import get_document_model

from .constants import EXTRACTED_IMAGES_COLLECTION_NAME
from .enums import ConversionStatus
from .models import DocumentConversion
from .services import (
    HybridPDFConverter,
    PDFConversionError,
)


logger = logging.getLogger(__name__)
Document = get_document_model()

if TYPE_CHECKING:
    from wagtail.documents.models import Document as WagtailDocument


def _convert_document_core(document_id: int) -> None:
    """
    Core document conversion logic shared between sync and async functions.

    Args:
        document_id: The ID of the Document to convert

    Raises:
        Document.DoesNotExist: If document not found
        PDFConversionError: If conversion fails
        Exception: For unexpected errors
    """
    try:
        # Get the document and update status to processing
        # NOTE: We're using a database row lock (select_for_update) to prevent race
        # conditions when multiple conversion tasks for the same document run
        # concurrently.
        # The first task to acquire the lock will check if conversion
        # is needed and update the status to PROCESSING. The lock is released when
        # this transaction commits. Any subsequent tasks will then acquire their own
        # lock, see the PROCESSING status, and skip conversion since
        # `should_convert()` returns False for documents with PROCESSING status.
        # This ensures only one conversion runs per document while maintaining
        # data consistency.
        with transaction.atomic():
            document = Document.objects.select_for_update().get(id=document_id)

            # Check if conversion is needed
            if not document.should_convert():
                logger.info(f"Document {document_id} does not need conversion")
                return

            # Update status to processing and record start time
            document.conversion_status = ConversionStatus.PROCESSING
            document.conversion_metrics = {
                **document.conversion_metrics,
                "conversion_started_at": timezone.now().isoformat(),
            }
            document.save(update_fields=["conversion_status", "conversion_metrics"])

        logger.info(f"Starting PDF conversion for document {document_id}")

        with document.open_file() as f:
            pdf_bytes = f.read()

        # Initialize converter and convert
        converter = HybridPDFConverter()
        collection_name = EXTRACTED_IMAGES_COLLECTION_NAME

        markdown_content, metrics = converter.convert_pdf_to_markdown(
            pdf_bytes=pdf_bytes,
            collection_name=collection_name,
            document_id=document_id,
        )

        # Add document-specific metadata to metrics
        metrics["original_filename"] = document.filename

        # Save the result
        with transaction.atomic():
            document.refresh_from_db()
            document.conversion_status = ConversionStatus.COMPLETED
            document.conversion_metrics = metrics
            document.save(update_fields=["conversion_status", "conversion_metrics"])

            DocumentConversion.objects.update_or_create(
                document=document,
                defaults={"converted_content": markdown_content},
            )

        logger.info(
            f"Successfully converted document {document_id}. "
            f"Processing time: {metrics.get('total_processing_time', 'unknown')}"
        )

    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        raise

    except PDFConversionError as e:
        logger.error(f"PDF conversion failed for document {document_id}: {e}")
        _mark_conversion_failed(document_id, str(e))
        raise

    except Exception as e:
        logger.exception(f"Unexpected error converting document {document_id}: {e}")
        _mark_conversion_failed(document_id, f"Unexpected error: {e}")
        raise


def convert_document_to_markdown_sync(document_id: int) -> None:
    """
    Convert a document to markdown format synchronously.

    Args:
        document_id: The ID of the Document to convert
    """
    _convert_document_core(document_id)


@task(backend="pdf_conversion")
def convert_document_to_markdown(document_id: int) -> None:
    """
    Convert a document to markdown format as a background task.

    Args:
        document_id: The ID of the Document to convert
    """
    try:
        _convert_document_core(document_id)
    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        raise
    except PDFConversionError as e:
        logger.error(f"PDF conversion failed for document {document_id}: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error converting document {document_id}: {e}")
        raise


def _mark_conversion_failed(document_id: int, error_message: str) -> None:
    """Mark a document conversion as failed."""
    try:
        with transaction.atomic():
            document = Document.objects.get(id=document_id)
            document.conversion_status = ConversionStatus.FAILED
            document.conversion_metrics = {
                "error": error_message,
                "failed_at": timezone.now().isoformat(),
            }
            document.save(
                update_fields=[
                    "conversion_status",
                    "conversion_metrics",
                ]
            )

    except Exception as e:
        logger.error(f"Failed to mark document {document_id} as failed: {e}")


def trigger_conversion_if_needed(document: "WagtailDocument") -> None:
    """
    Trigger conversion for a document if it needs it.

    This function checks the document's state and enqueues a conversion
    task if all conditions are met (is a PDF, not exempt, and has a
    'pending' or 'failed' status).

    Args:
        document: The Document instance to potentially convert
    """
    if document.should_convert():
        logger.info(f"Triggering conversion for document {document.id}")
        convert_document_to_markdown.enqueue(document.id)

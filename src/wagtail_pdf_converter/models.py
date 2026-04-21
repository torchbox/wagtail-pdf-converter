from typing import TYPE_CHECKING, Any, cast

import puremagic

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from wagtail.documents.models import AbstractDocument
from wagtail.documents.models import Document as WagtailDocument
from wagtail.search import index
from wagtail.utils.file import hash_filelike
from wagtailmarkdown.fields import MarkdownField

from .enums import ConversionStatus


if TYPE_CHECKING:
    from django.db.models.fields.files import FieldFile


class DocumentConversion(models.Model):
    """
    Stores the heavy Markdown payload generated from a PDF conversion.

    This model is intentionally separated from the Document table to prevent
    the large ``converted_content`` field from being loaded into memory on
    every queryset that touches documents (e.g. admin index, page renders with
    related documents). The row is created via ``update_or_create`` when a
    conversion completes and is never loaded unless explicitly accessed.
    """

    document = models.OneToOneField(
        settings.WAGTAILDOCS_DOCUMENT_MODEL,
        on_delete=models.CASCADE,
        related_name="pdf_conversion",
    )
    converted_content = MarkdownField(blank=True, null=True)
    allow_indexing = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Document Conversion")
        verbose_name_plural = _("Document Conversions")

    def __str__(self) -> str:
        return f"Conversion for {self.document}"


class PDFConversionMixin(models.Model):
    """
    A mixin for models that require PDF to accessible HTML conversion.

    This mixin is intended to be used with a model that has a `FileField`
    named `file`, such as a Wagtail Document model.

    It provides fields for tracking conversion status, exemption, and storing
    the converted content. It also includes methods to check if a document
    is a PDF, if it should be converted, and if it has successfully been
    converted.

    The heavy Markdown payload (converted content) is stored in the related
    :class:`DocumentConversion` model to avoid loading it into memory on
    every document queryset.
    """

    if TYPE_CHECKING:
        # Type hint for the file field that should be provided by the concrete model
        file: "FieldFile"

    admin_form_fields = WagtailDocument.admin_form_fields + (
        # We add all custom fields names to make them appear in the form:
        "conversion_exempt",
    )

    search_fields = AbstractDocument.search_fields + [
        index.SearchField("get_converted_content_for_search"),
    ]

    conversion_exempt = models.BooleanField(
        default=False,
        verbose_name=_("Exempt from accessible version"),
        help_text=_("Check this box to skip automatic conversion to accessible HTML format"),
    )
    conversion_status = models.CharField(
        max_length=20,
        choices=ConversionStatus.choices,
        default=ConversionStatus.PENDING,
        verbose_name=_("Conversion Status"),
    )
    conversion_metrics = models.JSONField(blank=True, default=dict)

    is_pdf = models.BooleanField(
        default=False,
        editable=False,
        help_text="Automatically determined based on file type on save.",
    )

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        Save the document and update PDF-related fields.

        This method handles the complex workflow of managing PDF detection and conversion
        status. It separates logic for new and existing documents.

        Workflow for NEW documents:
        1. Delegate to `_save_new_document` which performs initial save (writes file to disk).
        2. Check file content to determine `is_pdf`.
        3. Update `is_pdf` and `conversion_status` via a direct SQL `UPDATE` to
           avoid triggering the `post_save` signal again.

        Workflow for EXISTING documents:
        1. Delegate to `_save_and_update_existing_document` to handle all update logic.
        2. `_save_and_update_existing_document` detects file changes, updates metadata,
           and sets the correct conversion status.
        3. The final `super().save()` call saves the changes.
        """
        if self.pk is None:
            self._save_new_document(*args, **kwargs)
        else:
            self._save_and_update_existing_document(*args, **kwargs)

    def _save_new_document(self, *args: Any, **kwargs: Any) -> None:
        """
        Save a new document and update PDF-related fields.

        This method performs the initial save (to write the file to disk and get a pk),
        then determines the file type and sets the initial `is_pdf` and `conversion_status` fields.
        """
        # Save first to ensure file is on disk and we have a pk
        super().save(*args, **kwargs)

        self.is_pdf = self._is_pdf_by_content()

        # Exemption status has the highest priority, since it can be set manually in Wagtail admin
        # and we want to respect that setting.
        if self.conversion_exempt:
            self.conversion_status = ConversionStatus.EXEMPT
        else:
            # Update status to match the file type for a new, non-exempt document.
            if not self.is_pdf:
                # Non-PDFs are always NOT_APPLICABLE.
                self.conversion_status = ConversionStatus.NOT_APPLICABLE
            elif self.conversion_status == ConversionStatus.NOT_APPLICABLE:
                # If it's a PDF but was somehow marked NOT_APPLICABLE, correct it to PENDING.
                # This is a safeguard, as the default status for a new doc is PENDING.
                self.conversion_status = ConversionStatus.PENDING

        # Use direct SQL update to avoid triggering post_save signal again
        cast(Any, type(self)).objects.filter(pk=self.pk).update(
            is_pdf=self.is_pdf, conversion_status=self.conversion_status
        )

    def _save_and_update_existing_document(self, *args: Any, **kwargs: Any) -> None:
        """
        Update an existing document's PDF-related fields and save.

        This method handles all logic for updating an existing document:
        1. Detects file changes by comparing hashes
        2. Updates file metadata and re-detects PDF status if file changed
        3. Updates conversion status based on current state (exemption, file type, etc.)
        4. Saves the changes

        The conversion status update logic follows this priority order:
        - If conversion_exempt=True -> EXEMPT
        - If was EXEMPT but now un-exempted -> reset to PENDING (PDF) or NOT_APPLICABLE (non-PDF)
        - If non-PDF -> NOT_APPLICABLE
        - If file type changed from non-PDF to PDF -> PENDING
        - If PDF with NOT_APPLICABLE status -> PENDING
        - Otherwise preserve existing status (PENDING, PROCESSING, FAILED, COMPLETED)
        """
        try:
            old_instance = cast(Any, type(self)).objects.only("file_hash", "is_pdf").get(pk=self.pk)
            old_is_pdf = old_instance.is_pdf
            old_file_hash = old_instance.file_hash
        except type(self).DoesNotExist:
            # Should not happen for an existing document, but handle gracefully
            old_is_pdf = None
            old_file_hash = ""

        # Detect if file content changed by comparing hashes
        file_changed = False
        if self.file:
            open_file_func = getattr(self, "open_file", None)
            if open_file_func:
                with open_file_func() as f:
                    current_hash = hash_filelike(f)
                file_changed = current_hash != old_file_hash
            else:
                file_changed = True
        else:
            # If there's no file now, it has "changed" from having one
            file_changed = bool(old_file_hash)

        if file_changed:
            # Update file metadata (size and hash) and check if it's a PDF
            set_meta_func = getattr(self, "_set_document_file_metadata", None)
            if set_meta_func:
                set_meta_func()
            self.is_pdf = self._is_pdf_by_content()

        # Update conversion status based on the latest state.
        # The status is updated according to the following priority order:
        # 1. If conversion_exempt=True -> EXEMPT
        # 2. If was EXEMPT but now conversion_exempt=False -> reset to PENDING (PDF) or NOT_APPLICABLE (non-PDF)
        # 3. If non-PDF -> NOT_APPLICABLE
        # 4. If file type changed from non-PDF to PDF -> PENDING
        # 5. If PDF with NOT_APPLICABLE status -> PENDING
        # 6. Otherwise preserve existing status (PENDING, PROCESSING, FAILED, COMPLETED)

        # Handle exemption status
        if self.conversion_exempt:
            self.conversion_status = ConversionStatus.EXEMPT
        # If manually un-exempting a document that was EXEMPT, reset to appropriate status
        elif self.conversion_status == ConversionStatus.EXEMPT and not self.conversion_exempt:
            self.conversion_status = ConversionStatus.PENDING if self.is_pdf else ConversionStatus.NOT_APPLICABLE
        # Handle PDF vs non-PDF status
        elif not self.is_pdf:
            # Non-PDF files should always be marked as not applicable
            self.conversion_status = ConversionStatus.NOT_APPLICABLE
        # At this point, we know self.is_pdf is True.
        # Reset status to PENDING if it was previously a non-PDF or incorrectly marked.
        elif not old_is_pdf or self.conversion_status == ConversionStatus.NOT_APPLICABLE:
            # File changed from non-PDF to PDF, or was a PDF incorrectly marked as N/A
            self.conversion_status = ConversionStatus.PENDING
        # Otherwise preserve existing status (PENDING, PROCESSING, FAILED, COMPLETED)

        # Save the changes
        super().save(*args, **kwargs)

    def _is_pdf_by_content(self) -> bool:
        """Check if the document is a PDF file by content."""
        if not self.file:
            return False
        try:
            # To support cloud storage (e.g. S3), we use from_stream instead of from_file
            with self.file.open("rb") as f:
                mime_type = puremagic.from_stream(f, mime=True)
            return mime_type == "application/pdf"
        except (OSError, FileNotFoundError, ValueError, puremagic.PureError):
            # ValueError: raised when file is empty
            # OSError/FileNotFoundError: file doesn't exist or can't be read
            # PureError: puremagic can't identify the file type
            return False

    def get_converted_content_for_search(self) -> str | None:
        """Return converted content for Wagtail search indexing.

        Safely accesses the related ``DocumentConversion`` row. Returns ``None``
        when no conversion exists so Wagtail skips indexing this field rather
        than raising an exception.
        """
        try:
            return self.pdf_conversion.converted_content  # type: ignore[attr-defined]
        except Exception:
            return None

    def should_convert(self) -> bool:
        """Check if this document should be converted to accessible format."""
        return (
            self.is_pdf
            and not self.conversion_exempt
            and self.conversion_status in [ConversionStatus.PENDING, ConversionStatus.FAILED]
        )

    def has_converted_content(self) -> bool:
        """Check if document has been successfully converted."""
        return self.conversion_status == ConversionStatus.COMPLETED

    def get_html_url(self) -> str | None:
        """
        Return the URL for the HTML version of the document.
        """
        if self.has_converted_content():
            return reverse("wagtail_pdf_converter_document_html", kwargs={"document_id": getattr(self, "id", None)})
        return None

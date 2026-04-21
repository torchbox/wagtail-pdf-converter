from itertools import islice
from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand
from wagtail.documents import get_document_model

from ...enums import ConversionStatus


Document = get_document_model()

if TYPE_CHECKING:
    from wagtail.documents.models import Document as WagtailDocument


class Command(BaseCommand):
    help = "Updates the `is_pdf` flag and conversion status for all existing documents."

    def handle(self, *args, **options):
        batch_size = 1000
        document_ids = list(Document.objects.order_by("pk").values_list("pk", flat=True))
        total_docs = len(document_ids)

        if total_docs == 0:
            self.stdout.write(self.style.WARNING("No documents found."))
            return

        i = 0
        iterator = iter(document_ids)
        while document_ids := list(islice(iterator, batch_size)):
            batch = Document.objects.filter(pk__in=document_ids).order_by("pk")
            for document in batch:
                i += 1
                self.stdout.write(f"Processing document {i}/{total_docs} (ID: {document.id})")
                document = self.process_document(document)

            # Bulk update all documents at once
            Document.objects.bulk_update(
                batch,
                ["is_pdf", "conversion_status", "conversion_exempt"],
                batch_size=1000,
            )

    def process_document(self, document: "WagtailDocument") -> "WagtailDocument":
        is_pdf = document._is_pdf_by_content()

        # Determine conversion status
        # Priority order:
        # 1. If conversion_exempt=True -> EXEMPT
        # 2. If publication type is excluded -> EXEMPT (and set conversion_exempt=True)
        # 3. If not a PDF -> NOT_APPLICABLE
        # 4. If PDF and not exempt -> PENDING (or preserve existing status if PROCESSING/FAILED/COMPLETED)

        if document.conversion_exempt:
            # Already exempt (manual exemption)
            document.conversion_status = ConversionStatus.EXEMPT
        elif not is_pdf:
            # Not a PDF
            document.conversion_status = ConversionStatus.NOT_APPLICABLE
        elif document.conversion_status in [
            ConversionStatus.PROCESSING,
            ConversionStatus.FAILED,
            ConversionStatus.COMPLETED,
        ]:
            # Preserve existing status for PDFs that are in progress or completed
            pass
        else:
            # PDF that should be pending
            document.conversion_status = ConversionStatus.PENDING

        # Update the is_pdf flag
        document.is_pdf = is_pdf

        return document

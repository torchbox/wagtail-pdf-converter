"""
Management command to convert PDF documents to markdown format.
"""

import time

from django.core.management.base import BaseCommand, CommandError
from wagtail.documents import get_document_model

from ...conf import settings as conf_settings
from ...enums import ConversionStatus
from ...tasks import (
    convert_document_to_markdown,
    convert_document_to_markdown_sync,
)


Document = get_document_model()


class Command(BaseCommand):
    help = "Convert PDF documents to accessible markdown format"

    @property
    def query_helper(self):
        """Helper for document queries based on configuration."""
        return conf_settings.DOCUMENT_CONVERSION_QUERY_HELPER

    def add_arguments(self, parser):
        parser.add_argument(
            "--document-id",
            type=int,
            help="Convert a specific document by ID",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Convert all eligible documents (pending or failed)",
        )
        parser.add_argument(
            "--failed-only",
            action="store_true",
            help="Retry only failed conversions",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be converted without actually converting",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Check the conversion status of a document (use with --document-id)",
        )
        parser.add_argument(
            "--wait",
            action="store_true",
            help="Wait for conversion to complete instead of running in background (only works with --document-id)",
        )
        parser.add_argument(
            "--follow",
            action="store_true",
            help="Follow the conversion progress with live updates (only works with --document-id)",
        )

    def handle(self, *args, **options):
        # Validate argument combinations
        self._validate_arguments(options)

        if options["document_id"] and options["status"]:
            self.show_document_status(options["document_id"])
        elif options["document_id"]:
            self.convert_single_document(
                options["document_id"],
                options["dry_run"],
                options["wait"],
                options["follow"],
            )
        elif options["all"]:
            self.convert_all_documents(options["dry_run"])
        elif options["failed_only"]:
            self.convert_failed_documents(options["dry_run"])
        else:
            raise CommandError("You must specify either --document-id, --all, or --failed-only")

    def _validate_arguments(self, options):
        """Validate argument combinations."""
        # --wait and --follow can only be used with --document-id
        if (options["wait"] or options["follow"]) and not options["document_id"]:
            raise CommandError("--wait and --follow can only be used with --document-id")

        # --wait and --follow are mutually exclusive
        if options["wait"] and options["follow"]:
            raise CommandError("--wait and --follow cannot be used together")

        # --status can only be used with --document-id
        if options["status"] and not options["document_id"]:
            raise CommandError("--status can only be used with --document-id")

    def show_document_status(self, document_id: int):
        """Show the conversion status of a document."""
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist as e:
            raise CommandError(f"Document with ID {document_id} not found") from e

        if not document.is_pdf:
            self.stdout.write(self.style.WARNING(f"Document {document_id} is not a PDF"))
            return

        self.stdout.write(f"Document: {document.title} (ID: {document_id})")
        self.stdout.write(f"Status: {document.get_conversion_status_display()}")
        self.stdout.write(f"Exempt: {'Yes' if document.conversion_exempt else 'No'}")

        if document.has_converted_content():
            try:
                content_length = len(document.pdf_conversion.converted_content or "")
            except type(document).pdf_conversion.RelatedObjectDoesNotExist:
                content_length = 0
            self.stdout.write(f"Converted content: {content_length:,} characters")
        else:
            self.stdout.write("Converted content: None")

        if document.conversion_status == ConversionStatus.PROCESSING:
            self.stdout.write(self.style.WARNING("Conversion is currently in progress..."))

    def convert_single_document(self, document_id: int, dry_run: bool, wait: bool = False, follow: bool = False):
        """Convert a single document."""
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist as e:
            raise CommandError(f"Document with ID {document_id} not found") from e

        if not document.is_pdf:
            raise CommandError(f"Document {document_id} is not a PDF")

        if document.conversion_exempt:
            self.stdout.write(self.style.WARNING(f"Document {document_id} is exempt from conversion"))
            return

        if dry_run:
            self.stdout.write(f"Would convert: {document.title} (ID: {document_id})")
        else:
            self.stdout.write(f"Converting: {document.title} (ID: {document_id})")

            if wait or follow:
                # use the sync version

                if follow:
                    self._follow_conversion_progress(document_id)
                else:
                    self.stdout.write("Converting synchronously (this may take a while)...")
                    try:
                        convert_document_to_markdown_sync(document_id)
                        self.stdout.write(self.style.SUCCESS(f"Conversion completed for document {document_id}"))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Conversion failed for document {document_id}: {e}"))
            else:
                convert_document_to_markdown.enqueue(document_id)
                self.stdout.write(self.style.SUCCESS(f"Conversion started for document {document_id}"))
                self.stdout.write("Use --status to check progress, or --follow to watch in real-time")

    def _follow_conversion_progress(self, document_id: int):
        """Follow the conversion progress with live updates."""

        # Start the conversion
        convert_document_to_markdown.enqueue(document_id)

        self.stdout.write("Following conversion progress...")
        self.stdout.write("Press Ctrl+C to stop following (conversion will continue)")

        last_status = None
        start_time = time.time()

        try:
            while True:
                document = Document.objects.get(id=document_id)
                current_status = document.conversion_status

                if current_status != last_status:
                    elapsed = time.time() - start_time
                    self.stdout.write(f"[{elapsed:.1f}s] Status changed to: {document.get_conversion_status_display()}")
                    last_status = current_status

                if current_status in [
                    ConversionStatus.COMPLETED,
                    ConversionStatus.FAILED,
                ]:
                    if current_status == ConversionStatus.COMPLETED:
                        try:
                            content_length = len(document.pdf_conversion.converted_content or "")
                        except Exception:
                            content_length = 0
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Conversion completed! Generated {content_length:,} characters of markdown."
                            )
                        )
                    else:
                        self.stdout.write(self.style.ERROR("Conversion failed!"))
                    break

                time.sleep(2)  # Check every 2 seconds

        except KeyboardInterrupt:
            self.stdout.write("\nStopped following. Conversion may still be running in background.")
            self.stdout.write(f"Use: ./manage.py convert_documents --document-id {document_id} --status")
        except Document.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Document {document_id} was deleted during conversion"))

    def convert_all_documents(self, dry_run: bool):
        """Convert all eligible documents."""
        documents = self.query_helper.eligible_for_conversion()

        count = documents.count()
        if count == 0:
            self.stdout.write("No documents found for conversion")
            return

        if dry_run:
            self.stdout.write(f"Would convert {count} documents:")
            for doc in documents:
                self.stdout.write(f"  - {doc.title} (ID: {doc.id})")
        else:
            self.stdout.write(f"Starting conversion for {count} documents...")
            for doc in documents:
                self.stdout.write(f"Converting: {doc.title} (ID: {doc.id})")
                convert_document_to_markdown.enqueue(doc.id)

            self.stdout.write(self.style.SUCCESS(f"Conversion started for {count} documents"))

    def convert_failed_documents(self, dry_run: bool):
        """Retry failed conversions."""
        documents = self.query_helper.failed_conversions()

        count = documents.count()
        if count == 0:
            self.stdout.write("No failed conversions found")
            return

        if dry_run:
            self.stdout.write(f"Would retry {count} failed conversions:")
            for doc in documents:
                self.stdout.write(f"  - {doc.title} (ID: {doc.id})")
        else:
            self.stdout.write(f"Retrying {count} failed conversions...")
            for doc in documents:
                self.stdout.write(f"Retrying: {doc.title} (ID: {doc.id})")
                convert_document_to_markdown.enqueue(doc.id)

            self.stdout.write(self.style.SUCCESS(f"Retry started for {count} documents"))

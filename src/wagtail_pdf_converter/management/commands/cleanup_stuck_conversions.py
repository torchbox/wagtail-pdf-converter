"""
Management command to clean up documents stuck in processing status.

This command identifies documents that have been in the PROCESSING status for
longer than a configurable timeout period and marks them as FAILED. This is
useful for handling edge cases where conversion tasks are interrupted due to
infrastructure issues, deployments, or other unexpected failures.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from wagtail.documents import get_document_model

from wagtail_pdf_converter.conf import settings as conf_settings

from ...enums import ConversionStatus


Document = get_document_model()


class Command(BaseCommand):
    help = "Mark documents stuck in PROCESSING status as FAILED"

    def add_arguments(self, parser):
        default_timeout = conf_settings.PDF_CONVERSION_TIMEOUT_HOURS
        parser.add_argument(
            "--timeout-hours",
            type=int,
            default=default_timeout,
            help=(
                f"Number of hours a document can be in PROCESSING before being "
                f"marked as stuck (default: {default_timeout})"
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which documents would be marked as failed without actually updating them",
        )

    def handle(self, *args, **options):
        timeout_hours = options["timeout_hours"]
        dry_run = options["dry_run"]

        if timeout_hours <= 0:
            self.stdout.write(self.style.ERROR("Timeout hours must be a positive integer"))
            return

        # Calculate the cutoff time
        cutoff_time = timezone.now() - timedelta(hours=timeout_hours)

        # Find documents stuck in PROCESSING
        # We look for documents that:
        # 1. Have PROCESSING status
        # 2. Have a conversion_started_at timestamp older than the cutoff
        all_processing = Document.objects.filter(
            conversion_status=ConversionStatus.PROCESSING,
        ).order_by("id")

        # Filter in Python to check the conversion_metrics JSONField
        stuck_documents = []
        for doc in all_processing:
            # Get the conversion start time from metrics
            if started_at_str := doc.conversion_metrics.get("conversion_started_at"):
                # Parse the ISO format timestamp
                started_at = parse_datetime(started_at_str)

                if started_at:
                    if timezone.is_naive(started_at):
                        started_at = timezone.make_aware(started_at)

                    if started_at < cutoff_time:
                        stuck_documents.append((doc, started_at))

        count = len(stuck_documents)

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(f"No documents stuck in PROCESSING for more than {timeout_hours} hours")
            )
            return

        # Display information about stuck documents
        self.stdout.write(
            self.style.WARNING(f"\nFound {count} document(s) stuck in PROCESSING for more than {timeout_hours} hours:")
        )
        self.stdout.write("")

        for doc, started_at in stuck_documents:
            # Show how long it's been stuck
            time_stuck = timezone.now() - started_at
            status_msg = f"processing for {time_stuck.total_seconds() / 3600:.1f} hours"

            self.stdout.write(f"  - ID {doc.id}: {doc.title} ({status_msg})")

        if dry_run:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("DRY RUN: No documents were updated. Run without --dry-run to mark them as FAILED.")
            )
            return

        # Mark documents as FAILED
        error_message = (
            f"Conversion timeout: stuck in PROCESSING for more than {timeout_hours} hours. "
            f"Cleaned up at {timezone.now().isoformat()}"
        )

        # Update documents
        docs_to_update = []
        for doc, _ in stuck_documents:
            doc.conversion_status = ConversionStatus.FAILED
            doc.conversion_metrics["error"] = error_message
            doc.conversion_metrics["failed_at"] = timezone.now().isoformat()
            docs_to_update.append(doc)

        Document.objects.bulk_update(docs_to_update, ["conversion_status", "conversion_metrics"])
        updated_count = len(docs_to_update)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Successfully marked {updated_count} document(s) as FAILED"))

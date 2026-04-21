from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from wagtail.documents import get_document_model

from wagtail_pdf_converter import tasks
from wagtail_pdf_converter.conf import settings as conf_settings
from wagtail_pdf_converter.enums import ConversionStatus
from wagtail_pdf_converter.management.commands import convert_documents
from wagtail_pdf_converter.models import DocumentConversion
from wagtail_pdf_converter.utils import DocumentConversionQueryHelper


Document = get_document_model()


class CustomQueryHelper(DocumentConversionQueryHelper):
    @classmethod
    def eligible_for_conversion(cls):
        # Only allow documents with "eligible" in the title
        return super().eligible_for_conversion().filter(title__contains="eligible")


class TestCommandFiltering(TestCase):
    """Test that the management command respects the configured QueryHelper."""

    def setUp(self):
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"
        self.doc_eligible = Document.objects.create(
            title="eligible",
            file=SimpleUploadedFile("eligible.pdf", pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PENDING,
            conversion_exempt=False,
        )
        self.doc_ineligible = Document.objects.create(
            title="ignore me",
            file=SimpleUploadedFile("ineligible.pdf", pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PENDING,
            conversion_exempt=False,
        )

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "DOCUMENT_CONVERSION_QUERY_HELPER": "tests.test_management_commands.CustomQueryHelper",
        }
    )
    def test_command_respects_custom_query_helper(self):
        """Test that the command only converts documents from the custom QuerySet."""
        out = StringIO()
        # Use dry-run to avoid actually calling tasks, but check the count in stdout
        call_command("convert_documents", "--all", "--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("Would convert 1 documents:", output)
        self.assertIn("eligible (ID:", output)
        self.assertNotIn("ignore me", output)


class TestDocumentQueryHelper(TestCase):
    """Test the DocumentQueryHelper methods."""

    def setUp(self):
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"

        # Eligible
        self.pdf_pending = Document.objects.create(
            title="Pending PDF",
            file=SimpleUploadedFile("pending.pdf", pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PENDING,
            conversion_exempt=False,
        )
        self.pdf_failed = Document.objects.create(
            title="Failed PDF",
            file=SimpleUploadedFile("failed.pdf", pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.FAILED,
            conversion_exempt=False,
        )
        # Ineligible
        Document.objects.create(
            title="Completed PDF",
            file=SimpleUploadedFile("completed.pdf", pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.COMPLETED,
        )
        Document.objects.create(
            title="Exempt PDF",
            file=SimpleUploadedFile("exempt.pdf", pdf_content, content_type="application/pdf"),
            conversion_exempt=True,
        )
        Document.objects.create(
            title="Text Document",
            file=SimpleUploadedFile("text.txt", b"Hello", content_type="text/plain"),
        )
        Document.objects.create(
            title="Excluded Pub Type",
            file=SimpleUploadedFile("excluded.pdf", pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PENDING,
            conversion_exempt=True,
        )

    def test_eligible_for_conversion(self):
        """Test that the correct documents are identified for conversion."""
        Helper = conf_settings.DOCUMENT_CONVERSION_QUERY_HELPER
        qs = Helper.eligible_for_conversion()
        self.assertIn(self.pdf_pending, qs)
        self.assertIn(self.pdf_failed, qs)
        self.assertEqual(qs.count(), 2)

    def test_failed_conversions(self):
        """Test that only failed conversions are returned."""
        Helper = conf_settings.DOCUMENT_CONVERSION_QUERY_HELPER
        qs = Helper.failed_conversions()
        self.assertIn(self.pdf_failed, qs)
        self.assertEqual(qs.count(), 1)


class TestConvertDocumentsCommand(TestCase):
    """Test the convert_documents management command."""

    def setUp(self):
        self.pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"

        # Create test documents
        self.pdf_pending = Document.objects.create(
            title="Pending PDF",
            file=SimpleUploadedFile("pending.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PENDING,
            conversion_exempt=False,
        )

        self.pdf_failed = Document.objects.create(
            title="Failed PDF",
            file=SimpleUploadedFile("failed.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.FAILED,
            conversion_exempt=False,
        )

        self.pdf_completed = Document.objects.create(
            title="Completed PDF",
            file=SimpleUploadedFile("completed.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.COMPLETED,
            conversion_exempt=False,
        )
        DocumentConversion.objects.create(document=self.pdf_completed, converted_content="# Already converted")

        self.pdf_exempt = Document.objects.create(
            title="Exempt PDF",
            file=SimpleUploadedFile("exempt.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.EXEMPT,
            conversion_exempt=True,
        )

        self.txt_doc = Document.objects.create(
            title="Text Document",
            file=SimpleUploadedFile("text.txt", b"Hello world", content_type="text/plain"),
        )

    def test_convert_single_document_success(self):
        """Test converting a single document by ID."""
        out = StringIO()

        with (
            mock.patch(convert_documents.__name__ + ".convert_document_to_markdown") as mock_task,
            mock.patch.object(self.pdf_pending, "is_pdf", return_value=True),
        ):
            mock_enqueue = mock.Mock()
            mock_task.enqueue = mock_enqueue
            call_command("convert_documents", f"--document-id={self.pdf_pending.pk}", stdout=out)
            mock_enqueue.assert_called_once_with(self.pdf_pending.pk)

        output = out.getvalue()
        self.assertIn(f"Converting: {self.pdf_pending.title}", output)
        self.assertIn("Conversion started", output)

    def test_convert_single_document_not_found(self):
        """Test error when document ID doesn't exist."""
        with self.assertRaises(CommandError) as context:
            call_command("convert_documents", "--document-id=99999")

        self.assertIn("Document with ID 99999 not found", str(context.exception))

    def test_convert_single_document_not_pdf(self):
        """Test error when document is not a PDF."""
        with self.assertRaises(CommandError) as context:
            call_command("convert_documents", f"--document-id={self.txt_doc.pk}")

        self.assertIn("is not a PDF", str(context.exception))

    def test_convert_single_document_exempt(self):
        """Test warning when document is exempt."""
        out = StringIO()

        with mock.patch.object(self.pdf_exempt, "is_pdf", return_value=True):
            call_command("convert_documents", f"--document-id={self.pdf_exempt.pk}", stdout=out)

        output = out.getvalue()
        self.assertIn("is exempt from conversion", output)

    def test_convert_single_document_wait(self):
        """Test converting a single document with --wait."""
        out = StringIO()
        with mock.patch(convert_documents.__name__ + ".convert_document_to_markdown_sync") as mock_sync:
            call_command(
                "convert_documents",
                f"--document-id={self.pdf_pending.pk}",
                "--wait",
                stdout=out,
            )
            mock_sync.assert_called_once_with(self.pdf_pending.pk)
        self.assertIn("Converting synchronously", out.getvalue())
        self.assertIn("Conversion completed", out.getvalue())

    def test_convert_single_document_wait_failure(self):
        """Test --wait flag when sync conversion fails with an exception."""
        out = StringIO()
        with mock.patch(convert_documents.__name__ + ".convert_document_to_markdown_sync") as mock_sync:
            mock_sync.side_effect = Exception("API rate limit exceeded")
            call_command(
                "convert_documents",
                f"--document-id={self.pdf_pending.pk}",
                "--wait",
                stdout=out,
            )
        output = out.getvalue()
        self.assertIn("Conversion failed", output)
        self.assertIn("API rate limit exceeded", output)

    def test_convert_single_document_follow(self):
        """Test converting a single document with --follow."""
        out = StringIO()
        with mock.patch(convert_documents.__name__ + ".Command._follow_conversion_progress") as mock_follow:
            call_command(
                "convert_documents",
                f"--document-id={self.pdf_pending.pk}",
                "--follow",
                stdout=out,
            )
            mock_follow.assert_called_once_with(self.pdf_pending.pk)

    def test_show_document_status(self):
        """Test the --status flag."""
        out = StringIO()
        call_command(
            "convert_documents",
            f"--document-id={self.pdf_completed.pk}",
            "--status",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn(f"Document: {self.pdf_completed.title}", output)
        self.assertIn("Status: Completed", output)
        self.assertIn("Exempt: No", output)
        self.assertIn("Converted content:", output)

    def test_show_document_status_processing(self):
        """Test --status flag for a document currently being processed."""
        self.pdf_pending.conversion_status = ConversionStatus.PROCESSING
        self.pdf_pending.save()

        out = StringIO()
        call_command(
            "convert_documents",
            f"--document-id={self.pdf_pending.pk}",
            "--status",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Status: Processing", output)
        self.assertIn("Conversion is currently in progress", output)

    def test_show_document_status_no_content(self):
        """Test --status flag for a document with no converted content."""
        # Create a pending document with no converted content
        out = StringIO()
        call_command(
            "convert_documents",
            f"--document-id={self.pdf_pending.pk}",
            "--status",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Converted content: None", output)

    def test_invalid_argument_combinations(self):
        """Test mutually exclusive/dependent argument validation."""
        with self.assertRaisesMessage(CommandError, "--wait and --follow can only be used with --document-id"):
            call_command("convert_documents", "--all", "--wait")

        with self.assertRaisesMessage(CommandError, "--wait and --follow cannot be used together"):
            call_command("convert_documents", "--document-id=1", "--wait", "--follow")

        with self.assertRaisesMessage(CommandError, "--status can only be used with --document-id"):
            call_command("convert_documents", "--all", "--status")

    def test_convert_all_documents(self):
        """Test converting all eligible documents."""
        out = StringIO()

        with mock.patch(convert_documents.__name__ + ".convert_document_to_markdown") as mock_task:
            mock_enqueue = mock.Mock()
            mock_task.enqueue = mock_enqueue
            call_command("convert_documents", "--all", stdout=out)

            # Should convert pending and failed documents
            self.assertEqual(mock_enqueue.call_count, 2)
            mock_enqueue.assert_any_call(self.pdf_pending.pk)
            mock_enqueue.assert_any_call(self.pdf_failed.pk)

        output = out.getvalue()
        self.assertIn("Starting conversion for 2 documents", output)

    def test_convert_failed_only(self):
        """Test converting only failed documents."""
        out = StringIO()

        with mock.patch(convert_documents.__name__ + ".convert_document_to_markdown") as mock_task:
            mock_enqueue = mock.Mock()
            mock_task.enqueue = mock_enqueue
            call_command("convert_documents", "--failed-only", stdout=out)

            # Should only convert the failed document
            mock_enqueue.assert_called_once_with(self.pdf_failed.pk)

        output = out.getvalue()
        self.assertIn("Retrying 1 failed conversions", output)

    def test_dry_run_all(self):
        """Test dry run mode for all documents."""
        out = StringIO()

        with mock.patch(convert_documents.__name__ + ".convert_document_to_markdown") as mock_convert:
            call_command("convert_documents", "--all", "--dry-run", stdout=out)

            # Should not actually convert anything
            mock_convert.assert_not_called()

        output = out.getvalue()
        self.assertIn("Would convert 2 documents", output)
        self.assertIn(self.pdf_pending.title, output)
        self.assertIn(self.pdf_failed.title, output)

    def test_dry_run_single(self):
        """Test dry run mode for single document."""
        out = StringIO()

        with (
            mock.patch(convert_documents.__name__ + ".convert_document_to_markdown") as mock_convert,
            mock.patch.object(self.pdf_pending, "is_pdf", return_value=True),
        ):
            call_command(
                "convert_documents",
                f"--document-id={self.pdf_pending.pk}",
                "--dry-run",
                stdout=out,
            )

            # Should not actually convert
            mock_convert.assert_not_called()

        output = out.getvalue()
        self.assertIn(f"Would convert: {self.pdf_pending.title}", output)

    def test_no_arguments_error(self):
        """Test error when no arguments provided."""
        with self.assertRaises(CommandError) as context:
            call_command("convert_documents")

        self.assertIn(
            "You must specify either --document-id, --all, or --failed-only",
            str(context.exception),
        )

    def test_no_eligible_documents(self):
        """Test handling when no documents are eligible for conversion."""
        # Delete all our test documents
        Document.objects.all().delete()

        out = StringIO()
        call_command("convert_documents", "--all", stdout=out)

        output = out.getvalue()
        self.assertIn("No documents found for conversion", output)

    def test_no_failed_documents(self):
        """Test handling when no failed documents exist."""
        # Update the failed document to be completed
        self.pdf_failed.conversion_status = ConversionStatus.COMPLETED
        self.pdf_failed.save()

        out = StringIO()
        call_command("convert_documents", "--failed-only", stdout=out)

        output = out.getvalue()
        self.assertIn("No failed conversions found", output)


class TestUpdateDocumentConversionStatusCommand(TestCase):
    def setUp(self):
        self.pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"
        self.non_pdf_content = b"text file"

    def test_command_updates_statuses_correctly(self):
        """
        Test that the management command correctly updates the is_pdf flag and
        conversion_status for a variety of existing documents.
        """
        # 1. A PDF that should be Pending but is incorrectly N/A
        doc1 = Document.objects.create(
            title="Doc 1",
            is_pdf=False,
            conversion_status=ConversionStatus.NOT_APPLICABLE,
            file=ContentFile(self.pdf_content, name="doc1.pdf"),
        )

        # 2. A non-PDF that should be N/A but is incorrectly Pending
        doc2 = Document.objects.create(
            title="Doc 2",
            is_pdf=True,
            conversion_status=ConversionStatus.PENDING,
            file=ContentFile(self.non_pdf_content, name="doc2.txt"),
        )

        # 3. A document with manual exemption
        doc3 = Document.objects.create(
            title="Doc 3",
            conversion_exempt=True,  # Manually marked exempt
            file=ContentFile(self.pdf_content, name="doc3.pdf"),
        )

        # Run the management command
        out = StringIO()
        call_command("update_document_conversion_status", stdout=out)

        # Reload and assert correct states
        doc1.refresh_from_db()
        self.assertTrue(doc1.is_pdf)
        self.assertEqual(doc1.conversion_status, ConversionStatus.PENDING)

        doc2.refresh_from_db()
        self.assertFalse(doc2.is_pdf)
        self.assertEqual(doc2.conversion_status, ConversionStatus.NOT_APPLICABLE)

        doc3.refresh_from_db()
        self.assertTrue(doc3.conversion_exempt)  # Manual exemption preserved
        self.assertEqual(doc3.conversion_status, ConversionStatus.EXEMPT)

    @override_settings(WAGTAIL_PDF_CONVERTER={"AUTO_CONVERT_PDFS": True})
    def test_command_does_not_enqueue_documents(self):
        """
        Test that the command does NOT enqueue documents for conversion
        because bulk_update bypasses signals entirely.
        """
        doc = Document.objects.create(
            title="Test PDF",
            file=ContentFile(self.pdf_content, name="test.pdf"),
        )

        out = StringIO()

        with mock.patch(tasks.__name__ + ".trigger_conversion_if_needed") as mock_trigger:
            call_command("update_document_conversion_status", stdout=out)

            # Signals should not fire because bulk_update bypasses them
            mock_trigger.assert_not_called()

        output = out.getvalue()
        self.assertIn("Processing document 1/1", output)

        doc.refresh_from_db()
        self.assertTrue(doc.is_pdf)
        self.assertEqual(doc.conversion_status, ConversionStatus.PENDING)

    def test_command_preserves_existing_statuses(self):
        """
        Test that the command preserves existing statuses for documents that are
        PROCESSING, FAILED, or COMPLETED.
        """
        # Create documents with various statuses
        processing_pdf = Document.objects.create(
            title="Processing PDF",
            file=ContentFile(self.pdf_content, name="processing.pdf"),
            conversion_status=ConversionStatus.PROCESSING,
        )
        failed_pdf = Document.objects.create(
            title="Failed PDF",
            file=ContentFile(self.pdf_content, name="failed.pdf"),
            conversion_status=ConversionStatus.FAILED,
        )
        completed_pdf = Document.objects.create(
            title="Completed PDF",
            file=ContentFile(self.pdf_content, name="completed.pdf"),
            conversion_status=ConversionStatus.COMPLETED,
        )
        DocumentConversion.objects.create(document=completed_pdf, converted_content="# Already done")

        out = StringIO()
        call_command("update_document_conversion_status", stdout=out)

        # Verify statuses are preserved
        processing_pdf.refresh_from_db()
        self.assertEqual(processing_pdf.conversion_status, ConversionStatus.PROCESSING)

        failed_pdf.refresh_from_db()
        self.assertEqual(failed_pdf.conversion_status, ConversionStatus.FAILED)

        completed_pdf.refresh_from_db()
        self.assertEqual(completed_pdf.conversion_status, ConversionStatus.COMPLETED)


class TestCleanupStuckConversionsCommand(TestCase):
    """Test the cleanup_stuck_conversions management command."""

    def setUp(self):
        self.pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"

    def test_cleanup_stuck_documents(self):
        """Test that stuck documents are marked as failed."""

        # Create a document that's been stuck in PROCESSING for 4 hours
        old_time = timezone.now() - timedelta(hours=4)
        stuck_doc = Document.objects.create(
            title="Stuck PDF",
            file=SimpleUploadedFile("stuck.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PROCESSING,
            conversion_metrics={"conversion_started_at": old_time.isoformat()},
        )

        # Create a recent document in PROCESSING (should not be cleaned up)
        recent_doc = Document.objects.create(
            title="Recent PDF",
            file=SimpleUploadedFile("recent.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PROCESSING,
            conversion_metrics={"conversion_started_at": timezone.now().isoformat()},
        )

        # Run the cleanup command with 3 hour timeout
        out = StringIO()
        call_command("cleanup_stuck_conversions", "--timeout-hours=3", stdout=out)

        # Check that only the stuck document was marked as failed
        stuck_doc.refresh_from_db()
        self.assertEqual(stuck_doc.conversion_status, ConversionStatus.FAILED)
        self.assertIn("Conversion timeout", stuck_doc.conversion_metrics["error"])
        self.assertIn(
            "stuck in PROCESSING for more than 3 hours",
            stuck_doc.conversion_metrics["error"],
        )

        recent_doc.refresh_from_db()
        self.assertEqual(recent_doc.conversion_status, ConversionStatus.PROCESSING)

        # Check command output
        output = out.getvalue()
        self.assertIn("Found 1 document(s) stuck", output)
        self.assertIn("Successfully marked 1 document(s) as FAILED", output)

    def test_cleanup_dry_run(self):
        """Test that dry run doesn't modify any documents."""

        old_time = timezone.now() - timedelta(hours=4)
        stuck_doc = Document.objects.create(
            title="Stuck PDF",
            file=SimpleUploadedFile("stuck.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PROCESSING,
            conversion_metrics={"conversion_started_at": old_time.isoformat()},
        )

        # Run with dry-run
        out = StringIO()
        call_command("cleanup_stuck_conversions", "--timeout-hours=3", "--dry-run", stdout=out)

        # Document should not be modified
        stuck_doc.refresh_from_db()
        self.assertEqual(stuck_doc.conversion_status, ConversionStatus.PROCESSING)
        self.assertNotIn("error", stuck_doc.conversion_metrics)

        # Check output
        output = out.getvalue()
        self.assertIn("Found 1 document(s) stuck", output)
        self.assertIn("DRY RUN", output)
        self.assertNotIn("Successfully marked", output)

    def test_cleanup_no_stuck_documents(self):
        """Test output when no documents are stuck."""
        # Create a recent document in PROCESSING
        Document.objects.create(
            title="Recent PDF",
            file=SimpleUploadedFile("recent.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PROCESSING,
        )

        out = StringIO()
        call_command("cleanup_stuck_conversions", "--timeout-hours=3", stdout=out)

        output = out.getvalue()
        self.assertIn("No documents stuck in PROCESSING", output)

    def test_cleanup_invalid_timeout(self):
        """Test error handling for invalid timeout values."""
        out = StringIO()
        call_command("cleanup_stuck_conversions", "--timeout-hours=0", stdout=out)

        output = out.getvalue()
        self.assertIn("Timeout hours must be a positive integer", output)

    def test_cleanup_custom_timeout(self):
        """Test cleanup with custom timeout hours."""

        # Create a document stuck for 2 hours (not old enough for 3hr timeout)
        medium_old_time = timezone.now() - timedelta(hours=2)
        medium_doc = Document.objects.create(
            title="Medium Old PDF",
            file=SimpleUploadedFile("medium.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PROCESSING,
            conversion_metrics={"conversion_started_at": medium_old_time.isoformat()},
        )

        # Run with 1 hour timeout (should catch the document)
        out = StringIO()
        call_command("cleanup_stuck_conversions", "--timeout-hours=1", stdout=out)

        medium_doc.refresh_from_db()
        self.assertEqual(medium_doc.conversion_status, ConversionStatus.FAILED)

    @override_settings(WAGTAIL_PDF_CONVERTER={"PDF_CONVERSION_TIMEOUT_HOURS": 6})
    def test_cleanup_uses_settings_default(self):
        """Test that the command uses the settings default when no timeout specified."""

        # Create a document stuck for 4 hours
        old_time = timezone.now() - timedelta(hours=4)
        doc = Document.objects.create(
            title="Stuck PDF",
            file=SimpleUploadedFile("stuck.pdf", self.pdf_content, content_type="application/pdf"),
            conversion_status=ConversionStatus.PROCESSING,
            conversion_metrics={"conversion_started_at": old_time.isoformat()},
        )

        # Run without specifying timeout (should use settings default of 6 hours)
        out = StringIO()
        call_command("cleanup_stuck_conversions", stdout=out)

        # Document should NOT be marked as failed because it's only 4 hours old
        # and the default is 6 hours
        doc.refresh_from_db()
        self.assertEqual(doc.conversion_status, ConversionStatus.PROCESSING)

        output = out.getvalue()
        self.assertIn("No documents stuck in PROCESSING for more than 6 hours", output)

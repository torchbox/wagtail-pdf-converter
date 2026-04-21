from unittest import mock

from django.test import override_settings

from wagtail_pdf_converter import tasks
from wagtail_pdf_converter.enums import ConversionStatus
from wagtail_pdf_converter.models import DocumentConversion
from wagtail_pdf_converter.services.base import PDFConversionError
from wagtail_pdf_converter.utils import DocumentConversionQueryHelper

from .test_base import PDFTransformationTestCase


class CustomQueryHelper(DocumentConversionQueryHelper):
    @classmethod
    def eligible_for_conversion(cls):
        # Only allow documents with "convert" in the title
        return super().eligible_for_conversion().filter(title__contains="convert")


class TestSignalFiltering(PDFTransformationTestCase):
    """Test that the post_save signal respects the configured QueryHelper."""

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AUTO_CONVERT_PDFS": True,
            "DOCUMENT_CONVERSION_QUERY_HELPER": "tests.test_document_integration.CustomQueryHelper",
        }
    )
    @mock.patch("wagtail_pdf_converter.tasks.trigger_conversion_if_needed")
    def test_signal_respects_custom_query_helper(self, mock_trigger):
        """Test that the signal only triggers conversion for eligible documents."""
        # 1. Create a document that is NOT eligible according to CustomQueryHelper
        doc_ineligible = self.create_test_pdf_document(title="Ignore me")
        # Trigger post_save by saving again (since 'created' is handled specially in signal)
        doc_ineligible.save()
        self.assertFalse(mock_trigger.called)

        # 2. Create a document that IS eligible
        doc_eligible = self.create_test_pdf_document(title="Please convert me")
        doc_eligible.save()
        mock_trigger.assert_called_with(doc_eligible)


class TestCustomDocumentPDFConversion(PDFTransformationTestCase):
    """Test PDF conversion integration with CustomDocument model."""

    def test_document_model_helper_methods(self):
        """Test the helper methods on CustomDocument."""
        pdf_doc = self.create_test_pdf_document(
            title="Test PDF",
            conversion_exempt=False,
            conversion_status=ConversionStatus.PENDING,
        )

        self.assertTrue(pdf_doc.is_pdf)
        self.assertTrue(pdf_doc.should_convert())
        self.assertFalse(pdf_doc.has_converted_content())

        # Test with non-PDF document
        txt_doc = self.create_test_non_pdf_document(title="Test Text")

        self.assertFalse(txt_doc.is_pdf)
        self.assertFalse(txt_doc.should_convert())

        # Test exempt document
        exempt_doc = self.create_test_pdf_document(
            title="Exempt PDF",
            conversion_exempt=True,
        )

        self.assertTrue(exempt_doc.is_pdf)
        self.assertFalse(exempt_doc.should_convert())

    def test_conversion_status_transitions(self):
        """Test conversion status changes."""
        doc = self.create_test_pdf_document(title="Test PDF", conversion_status=ConversionStatus.PENDING)

        # Test completed conversion
        doc.conversion_status = ConversionStatus.COMPLETED
        doc.save(update_fields=["conversion_status"])
        DocumentConversion.objects.create(document=doc, converted_content="# Test Markdown Content")

        self.assertTrue(doc.has_converted_content())

        # Test failed conversion
        doc.conversion_status = ConversionStatus.FAILED
        doc.save(update_fields=["conversion_status"])

        self.assertFalse(doc.has_converted_content())


class TestPDFConversionTasks(PDFTransformationTestCase):
    """Test PDF conversion task functions."""

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch(tasks.__name__ + ".HybridPDFConverter")
    def test_convert_document_to_markdown_success(self, mock_converter_class):
        """Test successful document conversion."""
        # Set up mock converter using helper
        self.mock_converter_success(mock_converter_class)

        # Create document
        doc = self.create_test_pdf_document(title="Test PDF", conversion_status=ConversionStatus.PENDING)

        # Mock the file.open method to return our PDF content
        with self.mock_file_open(doc):
            # Use the synchronous version for testing
            tasks.convert_document_to_markdown_sync(doc.id)

        # Refresh from database
        doc.refresh_from_db()

        # Verify conversion completed
        self.assertEqual(doc.conversion_status, "completed")
        conversion = DocumentConversion.objects.get(document=doc)
        self.assertEqual(conversion.converted_content, "# Test Markdown Content\n\nThis is a test document.")

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch(tasks.__name__ + ".HybridPDFConverter")
    def test_convert_document_to_markdown_failure(self, mock_converter_class):
        """Test document conversion failure."""
        # Set up mock converter to raise an exception using helper
        self.mock_converter_failure(mock_converter_class, "Test error")

        # Create document
        doc = self.create_test_pdf_document(title="Test PDF", conversion_status=ConversionStatus.PENDING)

        # Mock the file.open method and expect PDFConversionError
        with self.mock_file_open(doc), self.assertRaises(PDFConversionError):
            tasks.convert_document_to_markdown_sync(doc.id)

        # Refresh from database
        doc.refresh_from_db()

        # Verify conversion failed
        self.assertEqual(doc.conversion_status, ConversionStatus.FAILED)
        self.assertFalse(DocumentConversion.objects.filter(document=doc).exists())

    def test_trigger_conversion_if_needed_eligible(self):
        """Test triggering conversion for eligible document."""
        doc = self.create_test_pdf_document(
            title="Test PDF",
            conversion_exempt=False,
            conversion_status=ConversionStatus.PENDING,
        )

        with mock.patch(tasks.__name__ + ".convert_document_to_markdown") as mock_task:
            mock_enqueue = mock.Mock()
            mock_task.enqueue = mock_enqueue
            tasks.trigger_conversion_if_needed(doc)
            mock_enqueue.assert_called_once_with(doc.id)

    def test_trigger_conversion_if_needed_exempt(self):
        """Test handling exempt document."""
        doc = self.create_test_pdf_document(
            title="Test PDF",
            conversion_exempt=True,
            conversion_status=ConversionStatus.PENDING,
        )

        with mock.patch(tasks.__name__ + ".convert_document_to_markdown") as mock_convert:
            tasks.trigger_conversion_if_needed(doc)
            mock_convert.assert_not_called()

            # Refresh and check status was updated
            doc.refresh_from_db()
            self.assertEqual(doc.conversion_status, ConversionStatus.EXEMPT)

    def test_trigger_conversion_if_needed_non_pdf(self):
        """Test handling non-PDF document."""
        doc = self.create_test_non_pdf_document(title="Test Text")

        with mock.patch(tasks.__name__ + ".convert_document_to_markdown") as mock_convert:
            tasks.trigger_conversion_if_needed(doc)
            mock_convert.assert_not_called()


class TestPDFConversionSignals(PDFTransformationTestCase):
    """Test PDF conversion signal handlers."""

    @override_settings(WAGTAIL_PDF_CONVERTER={"AUTO_CONVERT_PDFS": True})
    @mock.patch(tasks.__name__ + ".trigger_conversion_if_needed")
    def test_signal_not_triggered_on_new_pdf(self, mock_trigger):
        """Test signal is NOT triggered when new PDF is uploaded."""
        self.create_test_pdf_document(title="Test PDF", conversion_exempt=False)

        mock_trigger.assert_not_called()

    @override_settings(
        TASKS={
            "default": {
                "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
                "ENQUEUE_ON_COMMIT": True,
            }
        },
        WAGTAIL_PDF_CONVERTER={"AUTO_CONVERT_PDFS": True},
    )
    @mock.patch(tasks.__name__ + ".trigger_conversion_if_needed")
    def test_signal_triggered_on_save(self, mock_trigger):
        """Test signal is triggered when a new PDF is saved after creation."""
        # Test with ENQUEUE_ON_COMMIT=True to ensure transaction handling is correct
        with self.captureOnCommitCallbacks(execute=True):
            doc = self.create_test_pdf_document(title="Test PDF", conversion_exempt=False)

        # Signal should not be triggered on creation
        mock_trigger.assert_not_called()

        # Trigger on save
        with self.captureOnCommitCallbacks(execute=True):
            doc.save()
        mock_trigger.assert_called_once_with(doc)

    @mock.patch(tasks.__name__ + ".trigger_conversion_if_needed")
    def test_signal_not_triggered_on_non_pdf(self, mock_trigger):
        """Test signal is not triggered for non-PDF files."""
        self.create_test_non_pdf_document(title="Test Text")
        mock_trigger.assert_not_called()

    @override_settings(WAGTAIL_PDF_CONVERTER={"AUTO_CONVERT_PDFS": True})
    @mock.patch(tasks.__name__ + ".trigger_conversion_if_needed")
    def test_signal_triggered_on_exemption_change(self, mock_trigger):
        """Test signal is triggered when exemption status changes."""
        # Create an exempt document
        doc = self.create_test_pdf_document(title="Test PDF", conversion_exempt=True)

        # Signal should not fire on creation
        mock_trigger.assert_not_called()

        # Change exemption status
        doc.conversion_exempt = False
        doc.save()

        # Should trigger conversion since exemption was removed
        mock_trigger.assert_called_once_with(doc)

    @override_settings(WAGTAIL_PDF_CONVERTER={"AUTO_CONVERT_PDFS": False})
    @mock.patch(tasks.__name__ + ".trigger_conversion_if_needed")
    def test_signal_disabled_when_auto_conversion_off(self, mock_trigger):
        """Test signal handler exits early when AUTO_CONVERT_PDFS is False."""
        doc = self.create_test_pdf_document(title="Test PDF", conversion_exempt=False)

        # Signal should not trigger on creation or save
        mock_trigger.assert_not_called()
        doc.save()
        mock_trigger.assert_not_called()

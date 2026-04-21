from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase
from wagtail.documents import get_document_model

from wagtail_pdf_converter import tasks
from wagtail_pdf_converter.enums import ConversionStatus
from wagtail_pdf_converter.models import DocumentConversion
from wagtail_pdf_converter.services import PDFConversionError


Document = get_document_model()


class TestPDFConverterTasks(TestCase):
    def setUp(self):
        """Set up a test document for the test cases."""
        self.pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        self.document = Document.objects.create(
            title="Test Document",
            conversion_status=ConversionStatus.PENDING,
            file=ContentFile(self.pdf_content, name="test.pdf"),
        )

    @patch(tasks.__name__ + ".HybridPDFConverter")
    def test_convert_document_core_success(self, MockConverter):
        """
        Test the core conversion logic for a successful conversion.
        """

        mock_converter_instance = MockConverter.return_value
        mock_converter_instance.convert_pdf_to_markdown.return_value = (
            "# Test Markdown",
            {"Total Processing Time": "1.0s"},
        )

        tasks._convert_document_core(self.document.pk)

        self.document.refresh_from_db()
        self.assertEqual(self.document.conversion_status, ConversionStatus.COMPLETED)
        conversion = DocumentConversion.objects.get(document=self.document)
        self.assertEqual(conversion.converted_content, "# Test Markdown")
        mock_converter_instance.convert_pdf_to_markdown.assert_called_once()

    @patch(tasks.__name__ + ".HybridPDFConverter")
    def test_convert_document_core_failure(self, MockConverter):
        """
        Test the core conversion logic for a failed conversion.
        """

        mock_converter_instance = MockConverter.return_value
        mock_converter_instance.convert_pdf_to_markdown.side_effect = PDFConversionError("Test Error")

        with self.assertRaises(PDFConversionError):
            tasks._convert_document_core(self.document.pk)

        self.document.refresh_from_db()
        self.assertEqual(self.document.conversion_status, ConversionStatus.FAILED)

    def test_convert_document_core_no_document(self):
        """
        Test that `_convert_document_core` raises DoesNotExist for an invalid document ID.
        """
        with self.assertRaises(Document.DoesNotExist):
            tasks._convert_document_core(9999)

    @patch(tasks.__name__ + ".logger")
    @patch(tasks.__name__ + ".HybridPDFConverter")
    def test_convert_document_core_unexpected_error_and_retry_exhaustion(self, MockConverter, mock_logger):
        """
        Test that an unexpected error (like retry exhaustion) during conversion
        is logged and the document status is set to FAILED.
        """
        mock_converter_instance = MockConverter.return_value
        # This simulates any non-PDFConversionError exception, including
        # a tenacity.RetryError that would be raised after all retries fail.
        error_message = "Some unexpected error"
        mock_converter_instance.convert_pdf_to_markdown.side_effect = Exception(error_message)

        with self.assertRaisesRegex(Exception, error_message):
            tasks._convert_document_core(self.document.pk)

        self.document.refresh_from_db()
        self.assertEqual(self.document.conversion_status, ConversionStatus.FAILED)
        mock_logger.exception.assert_called_with(
            f"Unexpected error converting document {self.document.pk}: {error_message}"
        )

    @patch(tasks.__name__ + ".convert_document_to_markdown")
    def test_trigger_conversion_if_needed(self, mock_convert_task):
        """
        Test that `trigger_conversion_if_needed` enqueues a task if the document
        should be converted.
        """

        self.document.conversion_exempt = False
        self.document.save()

        tasks.trigger_conversion_if_needed(self.document)

        mock_convert_task.enqueue.assert_called_once_with(self.document.pk)

    @patch(tasks.__name__ + ".convert_document_to_markdown")
    def test_trigger_conversion_not_needed(self, mock_convert_task):
        """
        Test that `trigger_conversion_if_needed` does not enqueue a task if the
        document should not be converted.
        """

        self.document.conversion_exempt = True
        self.document.save()

        tasks.trigger_conversion_if_needed(self.document)

        mock_convert_task.enqueue.assert_not_called()
        self.document.refresh_from_db()
        self.assertEqual(self.document.conversion_status, ConversionStatus.EXEMPT)

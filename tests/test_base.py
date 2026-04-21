"""
Base test utilities for PDF transformation tests.
Provides shared setup, mocking patterns, and test data creation.
"""

import io

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from wagtail.documents import get_document_model

from wagtail_pdf_converter.enums import ConversionStatus
from wagtail_pdf_converter.services import PDFConversionError


Document = get_document_model()


class PDFTestMixin:
    """Shared test utilities for PDF conversion tests."""

    @classmethod
    def setUpTestData(cls):
        # Standard PDF content for testing
        cls.pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"

    def setUp(self):
        """Set up test data for each test method."""
        # Create standard test PDF file
        self.pdf_file = SimpleUploadedFile("test_document.pdf", self.pdf_content, content_type="application/pdf")

    def tearDown(self):
        super().tearDown()

        # Clean up any existing documents to ensure test isolation
        # First delete the actual files from the filesystem
        for document in Document.objects.all():
            try:
                if document.file:
                    document.file.delete(save=False)
            except (OSError, FileNotFoundError):
                # File might already be deleted or not exist, continue cleanup
                pass

        # Then delete the database records
        Document.objects.all().delete()

    def create_test_pdf_document(self, **kwargs):
        """
        Factory method to create test PDF documents with sensible defaults.

        Args:
            **kwargs: Override any field values for Document

        Returns:
            Document: Created document instance
        """
        defaults = {
            "title": "Test PDF Document",
            "file": SimpleUploadedFile(
                f"test_{len(Document.objects.all())}.pdf",
                self.pdf_content,
                content_type="application/pdf",
            ),
            "conversion_exempt": False,
            "conversion_status": ConversionStatus.PENDING,
        }
        defaults.update(kwargs)
        return Document.objects.create(**defaults)

    def create_test_non_pdf_document(self, **kwargs):
        """
        Factory method to create test non-PDF documents.

        Args:
            **kwargs: Override any field values for Document

        Returns:
            Document: Created document instance
        """
        defaults = {
            "title": "Test Text Document",
            "file": SimpleUploadedFile("test.txt", b"Hello world", content_type="text/plain"),
        }
        defaults.update(kwargs)
        return Document.objects.create(**defaults)

    def mock_converter_success(self, mock_converter_class):
        """
        Configure mock converter for successful conversion.

        Args:
            mock_converter_class: The mocked HybridPDFConverter class

        Returns:
            Mock: The configured mock converter instance
        """
        mock_converter = mock.Mock()
        mock_converter.convert_pdf_to_markdown.return_value = (
            "# Test Markdown Content\n\nThis is a test document.",
            {"Total Processing Time": "5.2 seconds"},
        )
        mock_converter_class.return_value = mock_converter
        return mock_converter

    def mock_converter_failure(self, mock_converter_class, error_message="Test error"):
        """
        Configure mock converter for failed conversion.

        Args:
            mock_converter_class: The mocked HybridPDFConverter class
            error_message: The error message to raise

        Returns:
            Mock: The configured mock converter instance
        """

        mock_converter = mock.Mock()
        mock_converter.convert_pdf_to_markdown.side_effect = PDFConversionError(error_message)
        mock_converter_class.return_value = mock_converter
        return mock_converter

    def mock_file_open(self, document, file_content=None):
        """
        Helper to mock document.open_file() for testing file operations.

        Args:
            document: The document instance to mock
            file_content: Content to return (defaults to self.pdf_content)

        Returns:
            Mock: The mock context manager
        """
        if file_content is None:
            file_content = self.pdf_content

        # Mock the open_file context manager to return a BytesIO object
        mock_file = io.BytesIO(file_content)
        mock_context_manager = mock.MagicMock()
        mock_context_manager.__enter__.return_value = mock_file
        mock_context_manager.__exit__.return_value = None

        return mock.patch.object(document, "open_file", return_value=mock_context_manager)


class PDFTransformationTestCase(PDFTestMixin, TestCase):
    """
    Base test case class for PDF transformation tests.
    Combines PDFTestMixin with Django TestCase.
    """

    pass

from django.core.files.base import ContentFile
from django.test import TestCase
from wagtail.documents import get_document_model

from wagtail_pdf_converter.enums import ConversionStatus


Document = get_document_model()


class TestConversionStatus(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Set up test data that doesn't change between tests."""
        cls.pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        cls.non_pdf_content = b"This is a text file."

    def test_is_pdf_flag_is_set_on_save(self):
        """Test that the `is_pdf` flag is correctly set when the model is saved."""
        pdf_doc = Document.objects.create(
            title="Test PDF",
            file=ContentFile(self.pdf_content, name="test.pdf"),
        )
        self.assertTrue(pdf_doc.is_pdf)

        non_pdf_doc = Document.objects.create(
            title="Test TXT",
            file=ContentFile(self.non_pdf_content, name="test.txt"),
        )
        self.assertFalse(non_pdf_doc.is_pdf)

    def test_non_pdf_gets_not_applicable_status(self):
        """Non-PDF files should have a 'not_applicable' conversion status."""
        doc = Document.objects.create(
            title="Test TXT",
            file=ContentFile(self.non_pdf_content, name="test.txt"),
        )
        self.assertEqual(doc.conversion_status, ConversionStatus.NOT_APPLICABLE)

    def test_pdf_gets_pending_status(self):
        """PDF files should default to a 'pending' conversion status."""
        doc = Document.objects.create(
            title="Test PDF",
            file=ContentFile(self.pdf_content, name="test.pdf"),
        )
        self.assertEqual(doc.conversion_status, ConversionStatus.PENDING)

    def test_exempt_pdf_gets_exempt_status(self):
        """An exempt PDF file should have an 'exempt' conversion status."""
        doc = Document.objects.create(
            title="Test PDF",
            conversion_exempt=True,
            file=ContentFile(self.pdf_content, name="test.pdf"),
        )
        self.assertEqual(doc.conversion_status, ConversionStatus.EXEMPT)

    def test_exempt_non_pdf_gets_exempt_status(self):
        """An exempt non-PDF file should have an 'exempt' status, which takes precedence."""
        doc = Document.objects.create(
            title="Test TXT",
            conversion_exempt=True,
            file=ContentFile(self.non_pdf_content, name="test.txt"),
        )
        self.assertEqual(doc.conversion_status, ConversionStatus.EXEMPT)

    def test_unexempting_pdf_resets_status_to_pending(self):
        """Changing a PDF from exempt to non-exempt should reset its status to 'pending'."""
        doc = Document.objects.create(
            title="Test PDF",
            conversion_exempt=True,
            file=ContentFile(self.pdf_content, name="test.pdf"),
        )
        self.assertEqual(doc.conversion_status, ConversionStatus.EXEMPT)

        doc.conversion_exempt = False
        doc.save()
        self.assertEqual(doc.conversion_status, ConversionStatus.PENDING)

    def test_unexempting_non_pdf_resets_status_to_not_applicable(self):
        """Changing a non-PDF from exempt to non-exempt should reset its status to 'not_applicable'."""
        doc = Document.objects.create(
            title="Test TXT",
            conversion_exempt=True,
            file=ContentFile(self.non_pdf_content, name="test.txt"),
        )
        self.assertEqual(doc.conversion_status, ConversionStatus.EXEMPT)

        doc.conversion_exempt = False
        doc.save()
        self.assertEqual(doc.conversion_status, ConversionStatus.NOT_APPLICABLE)

    def test_should_convert_logic(self):
        """Test the `should_convert()` method under various conditions."""
        # Pending PDF should be converted
        pending_pdf = Document.objects.create(
            title="Pending PDF",
            file=ContentFile(self.pdf_content, name="pending.pdf"),
        )
        self.assertTrue(pending_pdf.should_convert())

        # Failed PDF should be converted (for retries)
        failed_pdf = Document.objects.create(
            title="Failed PDF",
            conversion_status=ConversionStatus.FAILED,
            file=ContentFile(self.pdf_content, name="failed.pdf"),
        )
        self.assertTrue(failed_pdf.should_convert())

        # Exempt PDF should not be converted
        exempt_pdf = Document.objects.create(
            title="Exempt PDF",
            conversion_exempt=True,
            file=ContentFile(self.pdf_content, name="exempt.pdf"),
        )
        self.assertFalse(exempt_pdf.should_convert())

        # Non-PDF should not be converted
        non_pdf = Document.objects.create(
            title="Non PDF TXT",
            file=ContentFile(self.non_pdf_content, name="non_pdf.txt"),
        )
        self.assertFalse(non_pdf.should_convert())

        # Completed PDF should not be converted
        completed_pdf = Document.objects.create(
            title="Completed PDF",
            conversion_status=ConversionStatus.COMPLETED,
            file=ContentFile(self.pdf_content, name="completed.pdf"),
        )
        self.assertFalse(completed_pdf.should_convert())

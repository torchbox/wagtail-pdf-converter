import pytest

from tests.testproject.testapp.models import CustomDocument
from wagtail_pdf_converter.forms import PDFConverterDocumentForm


@pytest.mark.django_db
class TestPDFConverterDocumentForm:
    class DocumentForm(PDFConverterDocumentForm):
        class Meta(PDFConverterDocumentForm.Meta):
            model = CustomDocument
            fields = "__all__"

    def test_form_instantiates(self):
        """Test that the form can be instantiated without errors."""
        form = self.DocumentForm()
        assert form is not None

    def test_form_with_instance(self):
        """Test that the form can be instantiated with an existing document."""
        document = CustomDocument.objects.create(title="Test Document")
        form = self.DocumentForm(instance=document)
        assert form is not None
        assert form.instance == document

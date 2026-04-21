from wagtail.documents.models import AbstractDocument

from wagtail_pdf_converter.models import PDFConversionMixin


class CustomDocument(PDFConversionMixin, AbstractDocument):  # type: ignore[django-manager-missing]
    pass

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse

from tests.testproject.testapp.models import CustomDocument
from wagtail_pdf_converter.enums import ConversionStatus
from wagtail_pdf_converter.models import DocumentConversion


if TYPE_CHECKING:
    from django.test import Client as DjangoClient

User = get_user_model()


@pytest.mark.django_db
class TestDocumentHTMLView:
    @pytest.fixture(autouse=True)
    def setup_models(self):
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"

        self.non_indexed_doc = CustomDocument.objects.create(
            title="Foo",
            file=ContentFile(pdf_content, name="foo.pdf"),
        )
        DocumentConversion.objects.create(document=self.non_indexed_doc, allow_indexing=False)

        self.indexed_doc = CustomDocument.objects.create(
            title="Bar",
            file=ContentFile(pdf_content, name="bar.pdf"),
        )
        DocumentConversion.objects.create(document=self.indexed_doc, allow_indexing=True)

    def test_view_not_found(self, client: "DjangoClient"):
        """
        If a document does not exist, a 404 response should be returned.
        """
        url = reverse("wagtail_pdf_converter_document_html", kwargs={"document_id": 999})
        response = client.get(url)
        assert response.status_code == HTTPStatus.NOT_FOUND

    @override_settings(SEO_NOINDEX=False)
    def test_view_noindex_tag_default(self, client: "DjangoClient", default_site):
        default_site.hostname = "testserver"
        default_site.save(update_fields=["hostname"])

        url = reverse("wagtail_pdf_converter_document_html", kwargs={"document_id": self.non_indexed_doc.id})
        response = client.get(url)
        assert '<meta name="robots" content="noindex">' in response.content.decode()

    @override_settings(SEO_NOINDEX=False)
    def test_view_noindex_tag_when_indexing_allowed(self, client: "DjangoClient", default_site):
        default_site.hostname = "testserver"
        default_site.save(update_fields=["hostname"])

        url = reverse("wagtail_pdf_converter_document_html", kwargs={"document_id": self.indexed_doc.id})
        response = client.get(url)
        assert '<meta name="robots" content="noindex">' not in response.content.decode()


@pytest.mark.django_db
class TestAdminViews:
    @pytest.fixture(autouse=True)
    def setup_models(self):
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"
        txt_content = b"This is a plain text document, not a PDF."

        self.oldest_doc = CustomDocument.objects.create(
            title="Aardvark",
            conversion_status=ConversionStatus.PENDING,
            file=ContentFile(pdf_content, name="aardvark.pdf"),
        )

        self.middle_doc = CustomDocument.objects.create(
            title="Zootopia",
            conversion_status=ConversionStatus.EXEMPT,
            conversion_exempt=True,
            file=ContentFile(pdf_content, name="zootopia.pdf"),
        )

        self.another_middle_doc = CustomDocument.objects.create(
            title="Babylon",
            conversion_status=ConversionStatus.FAILED,
            file=ContentFile(pdf_content, name="babylon.pdf"),
        )

        self.newest_doc = CustomDocument.objects.create(
            title="Middle-Earth",
            conversion_status=ConversionStatus.COMPLETED,
            file=ContentFile(pdf_content, name="middle-earth.pdf"),
        )
        DocumentConversion.objects.create(document=self.newest_doc, converted_content="# Sample converted content")

        self.text_doc = CustomDocument.objects.create(
            title="Plain Text",
            file=ContentFile(txt_content, name="plain.txt"),
        )

    def test_document_index_ordering(self, client_superuser):
        response = client_superuser.get(reverse("wagtaildocs:index"))

        assert list(response.context["object_list"]) == [
            self.text_doc,
            self.newest_doc,
            self.another_middle_doc,
            self.middle_doc,
            self.oldest_doc,
        ]

    def test_document_index_status_column(self, client_superuser):
        response = client_superuser.get(reverse("wagtaildocs:index"))
        content = response.content.decode()
        assert "HTML version" in content
        assert "Pending&hellip;" in content
        assert "Exempt" in content
        assert "Conversion failed" in content
        assert "N/A" in content
        assert reverse("wagtail_pdf_converter_document_html", args=[self.newest_doc.pk]) in content
        assert reverse("wagtail_pdf_converter:retry_conversion", args=[self.another_middle_doc.pk]) in content

from http import HTTPStatus
from io import BytesIO

import pytest

from django.contrib.messages import get_messages
from django.core.files.images import ImageFile
from django.test import RequestFactory, override_settings
from django.urls import reverse
from PIL import Image as PILImage
from wagtail.images import get_image_model
from wagtail.models import Collection

from tests.testproject.testapp.models import CustomDocument
from wagtail_pdf_converter.admin_views import ConversionStatusColumn, CustomImageIndexView, PDFConverterIndexViewMixin
from wagtail_pdf_converter.constants import EXTRACTED_IMAGES_COLLECTION_NAME
from wagtail_pdf_converter.enums import ConversionStatus
from wagtail_pdf_converter.models import DocumentConversion


@pytest.mark.django_db
class TestConversionMetricsView:
    def test_context_data(self, client_superuser):
        """Test that the metrics view returns correct statistics."""
        # Create some test data
        # 1. Completed conversion with timing
        doc1 = CustomDocument.objects.create(
            title="Completed Doc 1",
            conversion_metrics={
                "processing_time": 10.5,
                "converted_at": "2023-01-01T12:00:00+00:00",
                "conversion_started_at": "2023-01-01T11:59:00+00:00",
            },
        )
        CustomDocument.objects.filter(pk=doc1.pk).update(conversion_status=ConversionStatus.COMPLETED)

        # 2. Completed conversion with timing
        doc2 = CustomDocument.objects.create(
            title="Completed Doc 2",
            conversion_metrics={
                "processing_time": 5.5,
                "converted_at": "2023-01-02T12:00:00+00:00",
                "conversion_started_at": "2023-01-02T11:59:00+00:00",
            },
        )
        CustomDocument.objects.filter(pk=doc2.pk).update(conversion_status=ConversionStatus.COMPLETED)

        # 3. Failed conversion
        doc3 = CustomDocument.objects.create(
            title="Failed Doc",
            conversion_metrics={"error": "Something went wrong"},
        )
        CustomDocument.objects.filter(pk=doc3.pk).update(conversion_status=ConversionStatus.FAILED)

        # 4. Pending conversion (should be ignored for stats)
        CustomDocument.objects.create(title="Pending Doc", conversion_status=ConversionStatus.PENDING)

        url = reverse("wagtail_pdf_converter:conversion-metrics")
        response = client_superuser.get(url)

        assert response.status_code == HTTPStatus.OK
        context = response.context

        # Check total completed conversions
        assert context["total_conversions"] == 2

        # Check failed conversions
        assert context["failed_conversions"] == 1

        # Check success rate (2 completed / (2 completed + 1 failed)) = 66.7%
        assert context["success_rate"] == 66.7

        # Check average processing time ((10.5 + 5.5) / 2) = 8.0
        assert context["avg_processing_time"] == 8.0

        # Check recent conversions list
        assert len(context["recent_conversions"]) == 2
        assert context["recent_conversions"][0].title == "Completed Doc 2"  # Most recent first

    def test_empty_metrics(self, client_superuser):
        """Test metrics view with no data."""
        url = reverse("wagtail_pdf_converter:conversion-metrics")
        response = client_superuser.get(url)

        assert response.status_code == HTTPStatus.OK
        context = response.context

        assert context["total_conversions"] == 0
        assert context["failed_conversions"] == 0
        assert context["avg_processing_time"] == 0
        assert context["success_rate"] == 0


@pytest.mark.django_db
class TestRetryConversionView:
    def test_retry_success(self, client_superuser):
        """Test that retry conversion resets status and redirects."""
        from django.core.files.base import ContentFile

        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n123\n%%EOF"

        document = CustomDocument.objects.create(
            title="Failed Doc",
            conversion_status=ConversionStatus.FAILED,
            conversion_metrics={"error": "Old error"},
            file=ContentFile(pdf_content, name="failed.pdf"),
        )

        url = reverse("wagtail_pdf_converter:retry_conversion", args=[document.pk])
        response = client_superuser.get(url)

        # Check redirect
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == reverse("wagtaildocs:index")

        # Verify document state updated
        document.refresh_from_db()
        assert document.conversion_status == ConversionStatus.PENDING
        # The retry_conversion view removes the 'error' key from conversion_metrics if present
        # (conversion_metrics is always a dict due to default=dict in the model field)
        assert "error" not in document.conversion_metrics

        # Verify success message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert str(messages[0]) == "Conversion retry initiated."

    def test_retry_non_existent_document(self, client_superuser):
        """Test retry with invalid document ID."""
        url = reverse("wagtail_pdf_converter:retry_conversion", args=[9999])
        response = client_superuser.get(url)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_retry_permission_denied(self, client):
        """Test that non-admin cannot retry conversion."""
        # Non-logged in user
        document = CustomDocument.objects.create(title="Failed Doc", conversion_status=ConversionStatus.FAILED)
        url = reverse("wagtail_pdf_converter:retry_conversion", args=[document.pk])
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == HTTPStatus.FOUND
        assert "/admin/login/" in response.url


@pytest.mark.django_db
class TestEditConversionContentView:
    def _make_completed_document(self):
        """Create a document with a DocumentConversion (simulates a completed conversion)."""
        document = CustomDocument.objects.create(title="Converted Doc")
        CustomDocument.objects.filter(pk=document.pk).update(conversion_status=ConversionStatus.COMPLETED)
        document.refresh_from_db()
        pdf_conversion = DocumentConversion.objects.create(
            document=document,
            converted_content="# Hello\n\nThis is the converted content.",
            allow_indexing=True,
        )
        return document, pdf_conversion

    def test_get_renders_form(self, client_superuser):
        document, _ = self._make_completed_document()
        url = reverse("wagtail_pdf_converter:edit_content", args=[document.pk])
        response = client_superuser.get(url)

        assert response.status_code == HTTPStatus.OK
        assert "form" in response.context
        assert "converted_content" in response.context["form"].fields
        assert "allow_indexing" in response.context["form"].fields
        assert response.context["document"].pk == document.pk

    def test_post_saves_and_redirects(self, client_superuser):
        document, _ = self._make_completed_document()
        url = reverse("wagtail_pdf_converter:edit_content", args=[document.pk])
        response = client_superuser.post(url, {"converted_content": "# Updated", "allow_indexing": True})

        assert response.status_code == HTTPStatus.FOUND
        assert response.url == reverse("wagtaildocs:edit", args=[document.pk])

        document.pdf_conversion.refresh_from_db()
        assert document.pdf_conversion.converted_content == "# Updated"

    def test_post_shows_success_message(self, client_superuser):
        document, _ = self._make_completed_document()
        url = reverse("wagtail_pdf_converter:edit_content", args=[document.pk])
        response = client_superuser.post(url, {"converted_content": "# Updated", "allow_indexing": False})

        msgs = list(get_messages(response.wsgi_request))
        assert len(msgs) == 1
        assert "Converted Doc" in str(msgs[0])

    def test_404_when_no_document_conversion(self, client_superuser):
        document = CustomDocument.objects.create(title="Not Converted Doc")
        url = reverse("wagtail_pdf_converter:edit_content", args=[document.pk])
        response = client_superuser.get(url)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_permission_denied_for_anonymous(self, client):
        document, _ = self._make_completed_document()
        url = reverse("wagtail_pdf_converter:edit_content", args=[document.pk])
        response = client.get(url)

        assert response.status_code == HTTPStatus.FOUND
        assert "/admin/login/" in response.url


@pytest.mark.django_db
class TestPDFConverterDocumentFormButtons:
    """
    PDFConverterDocumentForm is a BaseDocumentForm subclass.
    Wagtail uses modelform_factory to bind it to the concrete Document model at runtime,
    so tests must do the same.
    """

    def _make_form_class(self):
        from wagtail.documents.forms import get_document_form

        return get_document_form(CustomDocument)

    def test_edit_button_shown_when_completed(self):
        """The 'Edit accessible version' button appears when status is COMPLETED."""
        document = CustomDocument.objects.create(title="Doc")
        CustomDocument.objects.filter(pk=document.pk).update(conversion_status=ConversionStatus.COMPLETED)
        DocumentConversion.objects.create(document=document, converted_content="# Hello")
        document.refresh_from_db()

        form = self._make_form_class()(instance=document)
        assert "conversion_actions" in form.fields
        assert "edit-content" in form.fields["conversion_actions"].widget.content

    def test_edit_button_absent_when_not_completed(self):
        """The 'Edit accessible version' button is absent when status is not COMPLETED."""
        document = CustomDocument.objects.create(title="Doc", conversion_status=ConversionStatus.PENDING)

        form = self._make_form_class()(instance=document)
        assert "conversion_actions" not in form.fields

    def test_retry_button_shown_when_failed(self):
        """The 'Retry conversion' button appears when status is FAILED."""
        document = CustomDocument.objects.create(title="Doc")
        CustomDocument.objects.filter(pk=document.pk).update(conversion_status=ConversionStatus.FAILED)
        document.refresh_from_db()

        form = self._make_form_class()(instance=document)
        assert "conversion_actions" in form.fields
        assert "retry_conversion" in form.fields["conversion_actions"].widget.content

    def test_no_buttons_for_new_instance(self):
        """No conversion_actions field is injected for unsaved instances."""
        document = CustomDocument(title="New Doc")
        form = self._make_form_class()(instance=document)
        assert "conversion_actions" not in form.fields


class TestPDFConverterIndexViewMixinColumns:
    """PDFConverterIndexViewMixin.columns conditionally includes ConversionStatusColumn."""

    class _FakeBase:
        @property
        def columns(self):
            return []

    class _TestView(PDFConverterIndexViewMixin, _FakeBase):
        pass

    def test_status_column_included_by_default(self):
        """When CONVERSION_STATUS_DISPLAY is not set, column appears (show in both views)."""
        view = self._TestView()
        column_types = [type(c) for c in view.columns]
        assert ConversionStatusColumn in column_types

    @override_settings(WAGTAIL_PDF_CONVERTER={"CONVERSION_STATUS_DISPLAY": "index_view"})
    def test_status_column_included_when_index_view(self):
        """When CONVERSION_STATUS_DISPLAY is 'index_view', column appears."""
        view = self._TestView()
        column_types = [type(c) for c in view.columns]
        assert ConversionStatusColumn in column_types

    @override_settings(WAGTAIL_PDF_CONVERTER={"CONVERSION_STATUS_DISPLAY": "edit_view"})
    def test_status_column_excluded_when_edit_view(self):
        """When CONVERSION_STATUS_DISPLAY is 'edit_view', column is absent."""
        view = self._TestView()
        column_types = [type(c) for c in view.columns]
        assert ConversionStatusColumn not in column_types


@pytest.mark.django_db
class TestPDFConverterDocumentFormStatusDisplay:
    """PDFConverterDocumentForm shows a status field based on CONVERSION_STATUS_DISPLAY."""

    def _make_form_class(self):
        from wagtail.documents.forms import get_document_form

        return get_document_form(CustomDocument)

    def _make_pdf_document(self):
        doc = CustomDocument.objects.create(title="Test PDF")
        CustomDocument.objects.filter(pk=doc.pk).update(is_pdf=True)
        doc.refresh_from_db()
        return doc

    def test_status_field_shown_by_default_for_pdf(self):
        """When CONVERSION_STATUS_DISPLAY is not set, status field appears for PDFs."""
        doc = self._make_pdf_document()
        form = self._make_form_class()(instance=doc)
        assert "conversion_status_display" in form.fields

    @override_settings(WAGTAIL_PDF_CONVERTER={"CONVERSION_STATUS_DISPLAY": "edit_view"})
    def test_status_field_shown_when_edit_view_for_pdf(self):
        """When CONVERSION_STATUS_DISPLAY is 'edit_view', status field appears for PDFs."""
        doc = self._make_pdf_document()
        form = self._make_form_class()(instance=doc)
        assert "conversion_status_display" in form.fields

    @override_settings(WAGTAIL_PDF_CONVERTER={"CONVERSION_STATUS_DISPLAY": "index_view"})
    def test_status_field_absent_when_index_view_for_pdf(self):
        """When CONVERSION_STATUS_DISPLAY is 'index_view', status field is absent."""
        doc = self._make_pdf_document()
        form = self._make_form_class()(instance=doc)
        assert "conversion_status_display" not in form.fields

    def test_status_field_absent_for_non_pdf(self):
        """Status field is not shown for non-PDF documents regardless of setting."""
        doc = CustomDocument.objects.create(title="Non-PDF Doc")
        assert not doc.is_pdf
        form = self._make_form_class()(instance=doc)
        assert "conversion_status_display" not in form.fields

    def test_status_field_absent_for_new_instance(self):
        """Status field is not shown for unsaved (new) document instances."""
        doc = CustomDocument(title="New Doc")
        form = self._make_form_class()(instance=doc)
        assert "conversion_status_display" not in form.fields

    def test_status_field_content_shows_human_readable_status(self):
        """The status field widget renders the document's human-readable conversion status."""
        doc = self._make_pdf_document()
        form = self._make_form_class()(instance=doc)
        assert "conversion_status_display" in form.fields
        widget_content = form.fields["conversion_status_display"].widget.content
        assert doc.get_conversion_status_display() in widget_content


def _make_img_file():
    buf = BytesIO()
    PILImage.new("RGB", (10, 10), color="blue").save(buf, format="PNG")
    buf.seek(0)
    return ImageFile(buf, name="img.png")


def _create_img(title, collection):
    Image = get_image_model()
    img = Image(title=title, file=_make_img_file(), collection=collection)
    img._set_file_hash()
    img.save()
    return img


@pytest.mark.django_db
class TestCustomImageIndexView:
    """Unit tests for CustomImageIndexView.get_base_queryset filtering."""

    def _setup_images(self):
        root = Collection.get_first_root_node()
        pdf_col = root.add_child(name=EXTRACTED_IMAGES_COLLECTION_NAME)
        other_col = root.add_child(name="Site Images")
        pdf_img = _create_img("PDF img", pdf_col)
        other_img = _create_img("Site img", other_col)
        return pdf_col, pdf_img, other_img

    def _make_view(self, collection_id=None, superuser=None):
        factory = RequestFactory()
        url = "/admin/images/"
        if collection_id:
            url += f"?collection_id={collection_id}"
        request = factory.get(url)
        # A superuser is required: WagtailImagesIndexView.get_base_queryset() calls
        # permission_policy.instances_user_has_any_permission_for(request.user, ...)
        # which returns an empty queryset for AnonymousUser, making all cases
        # indistinguishable. The superuser fixture is defined in conftest.py.
        request.user = superuser
        view = CustomImageIndexView()
        # Use Django's setup() to properly initialise self.request, self.args,
        # self.kwargs rather than setting attributes manually.
        view.setup(request)
        return view

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": True})
    def test_excludes_pdf_images_when_setting_on_no_collection_filter(self, superuser):
        from wagtail_pdf_converter.conf import settings

        settings.reload()
        pdf_col, pdf_img, other_img = self._setup_images()
        view = self._make_view(superuser=superuser)

        qs = view.get_base_queryset()

        ids = list(qs.values_list("id", flat=True))
        assert other_img.id in ids
        assert pdf_img.id not in ids

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": True})
    def test_shows_all_when_setting_on_collection_filter_present(self, superuser):
        from wagtail_pdf_converter.conf import settings

        settings.reload()
        pdf_col, pdf_img, other_img = self._setup_images()
        view = self._make_view(collection_id=pdf_col.id, superuser=superuser)

        qs = view.get_base_queryset()

        ids = list(qs.values_list("id", flat=True))
        assert pdf_img.id in ids
        assert other_img.id in ids

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": False})
    def test_shows_all_when_setting_off_no_collection_filter(self, superuser):
        from wagtail_pdf_converter.conf import settings

        settings.reload()
        pdf_col, pdf_img, other_img = self._setup_images()
        view = self._make_view(superuser=superuser)

        qs = view.get_base_queryset()

        ids = list(qs.values_list("id", flat=True))
        assert pdf_img.id in ids
        assert other_img.id in ids

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": False})
    def test_shows_all_when_setting_off_collection_filter_present(self, superuser):
        from wagtail_pdf_converter.conf import settings

        settings.reload()
        pdf_col, pdf_img, other_img = self._setup_images()
        view = self._make_view(collection_id=pdf_col.id, superuser=superuser)

        qs = view.get_base_queryset()

        ids = list(qs.values_list("id", flat=True))
        assert pdf_img.id in ids
        assert other_img.id in ids

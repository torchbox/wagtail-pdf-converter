from typing import TYPE_CHECKING, Any

import django_filters

from django.contrib import messages
from django.db.models import Avg, FloatField
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from wagtail.admin.auth import require_admin_access
from wagtail.admin.ui.tables import Column
from wagtail.admin.views.generic.models import TemplateView
from wagtail.documents import get_document_model
from wagtail.documents.views.documents import (
    DocumentsFilterSet as WagtailDocumentsFilterSet,
)
from wagtail.documents.views.documents import IndexView as WagtailDocsIndexView
from wagtail.images.views.images import IndexView as WagtailImagesIndexView

from wagtail_pdf_converter.conf import settings as pdf_settings
from wagtail_pdf_converter.constants import ConversionStatusDisplay
from wagtail_pdf_converter.enums import ConversionStatus
from wagtail_pdf_converter.forms import ConversionContentForm
from wagtail_pdf_converter.models import DocumentConversion
from wagtail_pdf_converter.utils import exclude_pdf_images


if TYPE_CHECKING:
    from django.http import HttpRequest

Document = get_document_model()


@method_decorator(require_admin_access, name="dispatch")
class ConversionMetricsView(TemplateView):
    template_name = "wagtail_pdf_converter/admin/conversion_metrics.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Get all documents with successful conversions
        # We assume the document model has PDFConversionMixin fields
        documents = Document.objects.filter(
            conversion_status=ConversionStatus.COMPLETED,
            conversion_metrics__has_key="converted_at",
        ).exclude(conversion_metrics__isnull=True)

        # Calculate average processing time
        avg_time = documents.annotate(
            processing_time=Cast("conversion_metrics__processing_time", output_field=FloatField())
        ).aggregate(avg_time=Avg("processing_time"))["avg_time"]

        # Get recent conversions
        recent_conversions = documents.order_by("-conversion_metrics__converted_at")[:10]

        # Prepare stats
        total_converted = documents.count()
        # We check for the existence of the "error" key because a document might be
        # stuck in PROCESSING state but have an error recorded, and we want to count
        # these as failures.
        failed_conversions = Document.objects.filter(conversion_metrics__has_key="error").count()

        context.update(
            {
                "avg_processing_time": round(avg_time, 2) if avg_time else 0,
                "total_conversions": total_converted,
                "failed_conversions": failed_conversions,
                "recent_conversions": recent_conversions,
                "success_rate": round(
                    (
                        (total_converted / (total_converted + failed_conversions)) * 100
                        if (total_converted + failed_conversions) > 0
                        else 0
                    ),
                    1,
                ),
            }
        )

        return context


class ConversionStatusColumn(Column):
    cell_template_name = "wagtail_pdf_converter/admin/conversion_status_cell.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("conversion_status", label=_("HTML version"), **kwargs)

    def get_value(self, instance: Any) -> dict[str, Any]:
        # We assume instance has the mixin
        return {
            "status": getattr(instance, "conversion_status", None),
            "error": getattr(instance, "conversion_metrics", {}).get("error"),
            "id": instance.id,
            "started_at": getattr(instance, "conversion_metrics", {}).get("conversion_started_at"),
        }

    def get_cell_context_data(self, instance, parent_context: dict[str, Any]) -> dict[str, Any]:
        context = super().get_cell_context_data(instance, parent_context)
        value = self.get_value(instance)
        context["status"] = value["status"]
        context["error"] = value["error"]
        context["started_at"] = value["started_at"]
        context["view_url"] = reverse("wagtail_pdf_converter_document_html", args=(value["id"],))
        context["retry_url"] = reverse("wagtail_pdf_converter:retry_conversion", args=(value["id"],))
        return context


class DocumentsIndexViewFilterSet(WagtailDocumentsFilterSet):
    conversion_status = django_filters.ChoiceFilter(
        field_name="conversion_status",
        choices=ConversionStatus.choices,
        label=_("Conversion status"),
    )


class PDFConverterIndexViewMixin:
    """
    A mixin that adds PDF conversion features to Wagtail's document IndexView.

    Use this if you already have a custom IndexView subclass and want to add
    the PDF conversion status column and filter without replacing your view entirely.

    Example::

        from wagtail.documents.views.documents import IndexView
        from wagtail_pdf_converter.admin_views import PDFConverterIndexViewMixin


        class MyDocumentIndexView(PDFConverterIndexViewMixin, IndexView):
            pass
    """

    filterset_class = DocumentsIndexViewFilterSet

    @property
    def columns(self) -> list[Column]:
        # Use a copy to avoid mutating the base class list in place
        columns = super().columns[:]  # type: ignore[misc]
        display = pdf_settings.CONVERSION_STATUS_DISPLAY
        if display in (None, ConversionStatusDisplay.INDEX_VIEW):
            columns.append(ConversionStatusColumn(width="25%"))
        return columns


class CustomDocumentIndexView(PDFConverterIndexViewMixin, WagtailDocsIndexView):
    """Default document index view with PDF conversion status column and filter."""

    default_ordering = "-created_at"


class CustomImageIndexView(WagtailImagesIndexView):
    """Image index view that hides PDF-extracted images by default.

    Images in the ``EXTRACTED_IMAGES_COLLECTION_NAME`` collection are excluded
    from the listing unless the user has explicitly selected that collection via
    the ``collection_id`` filter.  Controlled by the ``FILTER_PDF_IMAGES``
    package setting (default ``True``).
    """

    def get_base_queryset(self):
        qs = super().get_base_queryset()
        if not pdf_settings.FILTER_PDF_IMAGES:
            return qs
        return exclude_pdf_images(qs, self.request)


@require_admin_access
def edit_conversion_content(request: "HttpRequest", document_id: int) -> Any:
    """
    A dedicated view for editing the converted_content of a DocumentConversion.
    Separated from the main document edit view to avoid loading large Markdown
    content into memory when it's not needed.
    """
    pdf_conversion = get_object_or_404(DocumentConversion.objects.select_related("document"), document_id=document_id)

    if request.method == "POST":
        form = ConversionContentForm(request.POST, instance=pdf_conversion)
        if form.is_valid():
            form.save()
            messages.success(
                request, _("Converted content updated for %(title)s") % {"title": pdf_conversion.document.title}
            )
            return redirect(reverse("wagtaildocs:edit", args=[document_id]))
    else:
        form = ConversionContentForm(instance=pdf_conversion)

    return render(
        request,
        "wagtail_pdf_converter/admin/edit_converted_content.html",
        {
            "document": pdf_conversion.document,
            "form": form,
        },
    )


@require_admin_access
def retry_conversion(request: "HttpRequest", document_id: int) -> Any:
    """Changes the document status to PENDING and resaves.
    It leaves existing converted content, if any."""
    document = get_object_or_404(Document, id=document_id)

    # Check if document has the required fields
    if not hasattr(document, "conversion_status"):
        messages.error(request, _("This document type does not support PDF conversion."))
        return redirect("wagtaildocs:index")

    document.conversion_status = ConversionStatus.PENDING
    if hasattr(document, "conversion_metrics") and isinstance(document.conversion_metrics, dict):
        document.conversion_metrics.pop("error", None)

    document.save()  # This will trigger conversion again

    messages.success(request, _("Conversion retry initiated."))
    return redirect("wagtaildocs:index")

from typing import Any

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from wagtail.documents import get_document_model

from .conf import settings as conf_settings


Document = get_document_model()


def document_html_view(request: Any, document_id: int) -> HttpResponse:
    """
    Display the accessible HTML version of a PDF document.

    Uses wagtail-markdown to render the converted content with proper
    styling that matches the site's design system.
    """
    document = get_object_or_404(Document, id=document_id)

    return render(
        request,
        "wagtail_pdf_converter/document.html",
        {
            "document": document,
            "base_template": conf_settings.BASE_TEMPLATE,
        },
    )

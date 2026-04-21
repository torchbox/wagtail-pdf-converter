from typing import Any

from django.urls import path

from .views import document_html_view


urlpatterns: list[Any] = [
    path(
        "<int:document_id>/html/",
        document_html_view,
        name="wagtail_pdf_converter_document_html",
    ),
]

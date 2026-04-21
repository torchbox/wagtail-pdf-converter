from typing import Any

from django.templatetags.static import static
from django.urls import include, path, reverse
from django.utils.html import format_html
from django.views.i18n import JavaScriptCatalog
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from . import admin_views
from .conf import settings as conf_settings
from .utils import exclude_pdf_images


@hooks.register("register_admin_urls")
def register_admin_urls() -> list[Any]:
    # Defines the URLs that will be under /admin/wagtail_pdf_converter/
    package_urls = [
        path(
            "jsi18n/",
            JavaScriptCatalog.as_view(packages=["wagtail_pdf_converter"]),
            name="javascript_catalog",
        ),
        path(
            "documents/<int:document_id>/edit-content/",
            admin_views.edit_conversion_content,
            name="edit_content",
        ),
        path(
            "documents/<int:document_id>/retry_conversion/",
            admin_views.retry_conversion,
            name="retry_conversion",
        ),
        path(
            "conversion-metrics/",
            admin_views.ConversionMetricsView.as_view(),
            name="conversion-metrics",
        ),
    ]

    # The list of URL patterns to return to Wagtail
    urlpatterns = [
        path(
            "wagtail_pdf_converter/",
            include(
                (package_urls, "wagtail_pdf_converter"),
                namespace="wagtail_pdf_converter",
            ),
        )
    ]

    # Conditional override of the document index
    # These must be added at the root level (e.g. /admin/documents/) to override Wagtail's defaults
    if conf_settings.ENABLE_ADMIN_EXTENSIONS:
        urlpatterns.extend(
            [
                path("documents/", admin_views.CustomDocumentIndexView.as_view(), name="index"),
                path(
                    "documents/results/",
                    admin_views.CustomDocumentIndexView.as_view(results_only=True),
                    name="index_results",
                ),
            ]
        )

    if conf_settings.FILTER_PDF_IMAGES:
        urlpatterns.extend(
            [
                path("images/", admin_views.CustomImageIndexView.as_view(), name="index"),
                path(
                    "images/results/",
                    admin_views.CustomImageIndexView.as_view(results_only=True),
                    name="index_results",
                ),
            ]
        )

    return urlpatterns


@hooks.register("register_admin_menu_item")
def register_conversion_metrics_menu_item() -> MenuItem:
    return MenuItem(
        "Conversion Metrics",
        reverse("wagtail_pdf_converter:conversion-metrics"),
        icon_name="doc-full",
        order=10000,
    )


@hooks.register("insert_global_admin_css")
def global_admin_css() -> str:
    if not conf_settings.ENABLE_ADMIN_EXTENSIONS:
        return ""

    return format_html('<link rel="stylesheet" href="{}">', static("wagtail_pdf_converter/css/admin.css"))


@hooks.register("construct_image_chooser_queryset")
def filter_pdf_images_from_chooser(queryset, request):
    if not conf_settings.FILTER_PDF_IMAGES:
        return queryset
    return exclude_pdf_images(queryset, request)

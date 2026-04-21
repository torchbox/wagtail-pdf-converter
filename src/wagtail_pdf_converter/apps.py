from django.apps import AppConfig


class PdfConverterConfig(AppConfig):
    label: str = "wagtail_pdf_converter"
    name: str = "wagtail_pdf_converter"
    default_auto_field: str = "django.db.models.BigAutoField"
    verbose_name: str = "Wagtail PDF Converter"

    def ready(self) -> None:
        """Import signals when the app is ready."""
        from . import signals  # noqa: F401

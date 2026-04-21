from django import forms
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail.documents.forms import BaseDocumentForm
from wagtailmarkdown.widgets import MarkdownTextarea

from wagtail_pdf_converter.conf import settings as pdf_settings
from wagtail_pdf_converter.constants import ConversionStatusDisplay
from wagtail_pdf_converter.enums import ConversionStatus
from wagtail_pdf_converter.models import DocumentConversion
from wagtail_pdf_converter.widgets import LinkWidget


class ConversionContentForm(forms.ModelForm):
    """
    A form for editing the converted content of a DocumentConversion instance.
    Used by the isolated ConversionContentEditView.
    """

    class Meta:
        model = DocumentConversion
        fields = ["converted_content", "allow_indexing"]
        widgets = {
            "converted_content": MarkdownTextarea(),
        }


class PDFConverterDocumentForm(BaseDocumentForm):
    """
    A base form for Wagtail Documents that provides better integration with the PDF Converter package.

    Usage:
    Set `WAGTAILDOCS_DOCUMENT_FORM_BASE` in your settings to point to this class:
    `WAGTAILDOCS_DOCUMENT_FORM_BASE = 'wagtail_pdf_converter.forms.PDFConverterDocumentForm'`
    """

    conversion_status_display = forms.CharField(
        label=_("Conversion status"),
        required=False,
        widget=LinkWidget,
    )

    conversion_actions = forms.CharField(
        label=_("PDF conversion actions"),
        required=False,
        widget=LinkWidget,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            del self.fields["conversion_status_display"]
            del self.fields["conversion_actions"]
            return

        self._setup_status_display_field()
        self._setup_conversion_actions_field()

    def _setup_status_display_field(self):
        display = pdf_settings.CONVERSION_STATUS_DISPLAY
        show = display in (None, ConversionStatusDisplay.EDIT_VIEW) and getattr(self.instance, "is_pdf", False)
        if show:
            status_text = self.instance.get_conversion_status_display()
            self.fields["conversion_status_display"].widget = LinkWidget(
                content=format_html("<p><strong>{}</strong></p>", status_text)
            )
        else:
            del self.fields["conversion_status_display"]

    def _setup_conversion_actions_field(self):
        buttons = []

        if self.instance.has_converted_content():
            edit_url = reverse("wagtail_pdf_converter:edit_content", args=[self.instance.pk])
            buttons.append(
                format_html(
                    '<a href="{}" target="_blank" class="button button-small button-secondary"'
                    ' style="margin-right: 10px;">Edit accessible version</a>',
                    edit_url,
                )
            )

        if self.instance.conversion_status in (ConversionStatus.FAILED, ConversionStatus.COMPLETED):
            retry_url = reverse("wagtail_pdf_converter:retry_conversion", args=[self.instance.pk])
            buttons.append(
                format_html(
                    '<a href="{}" class="button button-small button-secondary">Retry conversion</a>',
                    retry_url,
                )
            )

        if buttons:
            self.fields["conversion_actions"].widget = LinkWidget(content="".join(str(b) for b in buttons))
        else:
            del self.fields["conversion_actions"]

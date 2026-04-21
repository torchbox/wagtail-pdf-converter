from django.forms.widgets import Widget
from django.utils.safestring import mark_safe


class LinkWidget(Widget):
    """
    A display-only widget that renders static HTML content (links/buttons).
    The content is set at construction time and is rendered regardless of
    whether the form is bound or unbound, so buttons remain visible on
    POST resubmit (e.g. when the form has validation errors on other fields).
    """

    def __init__(self, content="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.content = content

    def render(self, name, value, attrs=None, renderer=None):
        return mark_safe(self.content)  # noqa: S308

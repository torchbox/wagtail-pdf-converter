"""
Custom template tags for rendering PDF-converted markdown with post-processing.
"""

from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe
from wagtailmarkdown.utils import render_markdown


register = template.Library()


@register.filter(name="pdf_markdown")
def pdf_markdown(value: Any) -> Any:
    """
    Render markdown with post-processing to enhance HTML elements.

    This extends wagtailmarkdown's render_markdown by applying post-processing to HTML
    elements that may only be available after markdown conversion. Currently adds:
    - Table wrapping: Wraps tables in container divs for horizontal scrolling
    - Blockquote classes: Adds 'blockquote' class to reuse existing component styles

    We do this because Gemini outputs markdown syntax (e.g., | ... |
    for tables, > for blockquotes) which gets converted to HTML by the markdown processor.
    """
    # Handle None/empty values
    if value is None or value == "":
        return value

    # First, render the markdown to HTML using wagtailmarkdown's standard pipeline
    # This respects all WAGTAILMARKDOWN settings (extensions, sanitization, etc.)
    html = render_markdown(value)

    if not html:
        return html

    soup = BeautifulSoup(html, "html.parser")

    # Find all table elements
    for table in soup.find_all("table"):
        # Check if this table is already inside a table-container
        parent = table.parent
        if parent and parent.name == "div" and "table-container" in parent.get("class", []):
            # Already wrapped, skip it
            continue

        # Wrap the table in a div with class="table-container"
        wrapper = soup.new_tag("div")
        wrapper["class"] = ["table-container"]
        table.wrap(wrapper)

    # Add blockquote class to all blockquote elements
    for blockquote in soup.find_all("blockquote"):
        existing_classes = blockquote.get("class", [])
        if "blockquote" not in existing_classes:
            existing_classes.append("blockquote")
            blockquote["class"] = existing_classes

    # Note: We use mark_safe here because the HTML has already been sanitized
    # by wagtailmarkdown's render_markdown function.
    return mark_safe(str(soup))  # noqa: S308


@register.filter(expects_localtime=True)
def parse_isodatetime(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value)
    return timezone.now()

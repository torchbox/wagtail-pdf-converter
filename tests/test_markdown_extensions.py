"""
Tests for custom Python Markdown extensions.
"""

import markdown

from wagtail_pdf_converter.markdown_extensions import HeadingAnchorExtension, makeExtension


def test_heading_with_id_gets_wrapped_in_anchor():
    """Headings with IDs should have their content wrapped in anchor links."""
    # Use toc extension which auto-generates IDs for headings
    md = markdown.Markdown(extensions=["toc", HeadingAnchorExtension()])
    text = "## Section Title"
    result = md.convert(text)

    # Should contain the heading with ID and anchor link wrapping the content
    assert 'id="section-title"' in result
    assert '<a class="heading-anchor" href="#section-title">Section Title</a>' in result


def test_heading_without_id_not_wrapped():
    """Headings without IDs should not be wrapped in anchor links."""
    md = markdown.Markdown(extensions=[HeadingAnchorExtension()])
    text = "## Regular Heading"
    result = md.convert(text)

    # Should contain the heading
    assert "<h2>Regular Heading</h2>" in result
    # Should NOT contain an anchor link
    assert "heading-anchor" not in result


def test_multiple_headings_with_ids_all_wrapped():
    """Multiple headings with IDs should all be wrapped."""
    # Use toc extension which auto-generates IDs for headings
    md = markdown.Markdown(extensions=["toc", HeadingAnchorExtension()])
    text = """
## First Section

Some content.

## Second Section

More content.
"""
    result = md.convert(text)

    # Both headings should have IDs and anchor links
    assert '<a class="heading-anchor" href="#first-section">First Section</a>' in result
    assert '<a class="heading-anchor" href="#second-section">Second Section</a>' in result


def test_heading_with_inline_formatting_preserved():
    """Headings with inline formatting (bold, italic) should preserve formatting."""
    # Use toc extension which auto-generates IDs for headings
    md = markdown.Markdown(extensions=["toc", HeadingAnchorExtension()])
    text = "## **Bold** and *Italic* Text"
    result = md.convert(text)

    # Should preserve formatting inside the anchor link
    assert 'class="heading-anchor"' in result
    assert "<strong>Bold</strong>" in result
    assert "<em>Italic</em>" in result


def test_different_heading_levels_all_handled():
    """All heading levels (h1-h6) should be handled."""
    # Use toc extension which auto-generates IDs for headings
    md = markdown.Markdown(extensions=["toc", HeadingAnchorExtension()])
    text = """
# H1 Title
## H2 Title
### H3 Title
#### H4 Title
##### H5 Title
###### H6 Title
"""
    result = md.convert(text)

    # All headings should have anchor links
    assert result.count('class="heading-anchor"') == 6


def test_heading_already_with_heading_anchor_not_double_wrapped():
    """Headings that already contain heading anchor links should not be double-wrapped."""
    md = markdown.Markdown(extensions=[HeadingAnchorExtension()])
    # Create markdown that already has a heading anchor (using HTML)
    text = '<h2 id="section-1"><a href="#section-1" class="heading-anchor">Existing Link</a></h2>'
    result = md.convert(text)

    # Should only have one anchor link
    assert result.count('<a href="#section-1"') == 1
    # Should keep the heading-anchor class
    assert result.count('class="heading-anchor"') == 1


def test_heading_with_legitimate_content_link_gets_wrapped():
    """Headings with legitimate content links should still get heading anchor wrapper."""
    md = markdown.Markdown(extensions=["attr_list", HeadingAnchorExtension()])
    text = "## See [the report](https://example.com/report) {: #section-1 }"
    result = md.convert(text)

    # Should have both the heading anchor and the content link
    assert 'href="#section-1"' in result and 'href="https://example.com/report"' in result


def test_extension_works_with_other_extensions():
    """Extension should work alongside other markdown extensions."""
    # Use toc extension which auto-generates IDs for headings
    md = markdown.Markdown(
        extensions=[
            "toc",  # Auto-generates IDs for headings
            HeadingAnchorExtension(),
        ]
    )
    text = "## Section Title"
    result = md.convert(text)

    # Should work correctly with toc extension
    assert 'class="heading-anchor"' in result


def test_makeExtension_factory_function():
    """The makeExtension factory function should create an extension instance."""
    extension = makeExtension()
    assert isinstance(extension, HeadingAnchorExtension)

    # Should work when used with markdown
    md = markdown.Markdown(extensions=["toc", extension])
    text = "## Test Heading"
    result = md.convert(text)

    # Should work correctly
    assert 'class="heading-anchor"' in result

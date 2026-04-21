"""
Tests for PDF converter template tags.
"""

from django.test import TestCase

from wagtail_pdf_converter.templatetags.pdf_markdown_tags import pdf_markdown


class TestPDFMarkdownTemplateTag(TestCase):
    """Tests for the pdf_markdown template tag."""

    def test_empty_value_returns_empty(self):
        """Empty or None values should be returned as-is."""
        self.assertEqual(pdf_markdown(""), "")
        self.assertEqual(pdf_markdown(None), None)

    def test_table_without_wrapper_gets_wrapped(self):
        """Tables without table-container wrapper should be wrapped."""
        markdown = """
| Column 1 | Column 2 |
|----------|----------|
| Data 1   | Data 2   |
"""
        result = pdf_markdown(markdown)

        # Should contain a table
        self.assertIn("<table>", result)
        # Should be wrapped in table-container
        self.assertIn('<div class="table-container">', result)
        # The div should wrap the table (check that table comes after the opening div tag)
        container_index = result.index('<div class="table-container">')
        table_index = result.index("<table>")
        self.assertLess(container_index, table_index, "table-container div should come before table")

    def test_already_wrapped_table_not_double_wrapped(self):
        """Tables already wrapped in table-container should not be double-wrapped."""
        # Note: md_in_html extension requires markdown="1" attribute to parse markdown inside HTML
        markdown = """
<div class="table-container" markdown="1">

| Column 1 | Column 2 |
|----------|----------|
| Data 1   | Data 2   |

</div>
"""
        result = pdf_markdown(markdown)

        # Should contain exactly one table-container div
        self.assertEqual(result.count('class="table-container"'), 1)
        # Should contain the table
        self.assertIn("<table>", result)

    def test_multiple_tables_all_wrapped(self):
        """Multiple unwrapped tables should all be wrapped."""
        markdown = """
First table:

| Col A | Col B |
|-------|-------|
| A1    | B1    |

Second table:

| Col X | Col Y |
|-------|-------|
| X1    | Y1    |
"""
        result = pdf_markdown(markdown)

        # Should have two tables
        self.assertEqual(result.count("<table>"), 2)
        # Should have two table-container wrappers
        self.assertEqual(result.count('class="table-container"'), 2)

    def test_table_with_formatting(self):
        """Tables with bold, italic, etc. should render correctly."""
        markdown = """
| **Bold** | *Italic* | `Code` |
|----------|----------|--------|
| Normal   | Text     | Here   |
"""
        result = pdf_markdown(markdown)

        self.assertIn("<table>", result)
        self.assertIn("<strong>Bold</strong>", result)
        self.assertIn("<em>Italic</em>", result)
        self.assertIn("<code>Code</code>", result)
        # Should be wrapped
        self.assertIn('class="table-container"', result)

    def test_blockquote_gets_class_added(self):
        """Blockquotes should have 'blockquote' class added."""
        markdown = """
> This is a simple quote.
> It is continued on the next line.
"""
        result = pdf_markdown(markdown)

        # Should contain a blockquote
        self.assertIn("<blockquote", result)
        # Should have blockquote class added
        self.assertIn('class="blockquote"', result)

    def test_multiple_blockquotes_all_get_class(self):
        """Multiple blockquotes should all get the blockquote class."""
        markdown = """
First quote:

> This is the first quote.

Second quote:

> This is the second quote.
"""
        result = pdf_markdown(markdown)

        # Should have two blockquotes
        self.assertEqual(result.count("<blockquote"), 2)
        # Both should have the class
        self.assertEqual(result.count('class="blockquote"'), 2)

    def test_blockquote_with_existing_class_not_duplicated(self):
        """Blockquotes with existing classes should not duplicate 'blockquote' class."""
        markdown = """
<blockquote class="existing-class" markdown="1">
This is a blockquote with an existing class.
</blockquote>
"""
        result = pdf_markdown(markdown)

        # Should have blockquote class added
        self.assertIn('class="existing-class blockquote"', result)
        # Should not be duplicated if run through the filter again
        second_pass = pdf_markdown(result)
        # Count how many times "blockquote" appears as a class value
        self.assertEqual(second_pass.count('"existing-class blockquote"'), 1)

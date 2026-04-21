"""
Custom Python Markdown extensions for PDF-converted content.
"""

import xml.etree.ElementTree as etree

from typing import Any

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor


class HeadingAnchorTreeprocessor(Treeprocessor):
    """
    Tree processor that wraps heading content in anchor links for headings with IDs.

    This makes headings clickable for sharing, while maintaining
    normal heading appearance.
    """

    def run(self, root: etree.Element) -> None:
        """
        Process the ElementTree, wrapping heading content in anchor links.

        For headings with IDs, wraps their content in an <a> tag with:
        - href pointing to the heading's ID
        - class="heading-anchor" for styling
        """
        # Find all headings (h1-h6)
        for heading in root.iter():
            if heading.tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                heading_id = heading.get("id")
                if heading_id:
                    # Check if the heading already contains a heading anchor link
                    # (e.g., if it was already processed). Allow legitimate content links.
                    existing_anchor = heading.find("a")
                    if existing_anchor is not None and "heading-anchor" in existing_anchor.get("class", ""):
                        continue

                    # Create an anchor link that wraps the heading's content
                    anchor = etree.Element("a")
                    anchor.set("href", f"#{heading_id}")
                    anchor.set("class", "heading-anchor")

                    # Move all content (text and child elements) into the anchor
                    # We need to preserve the heading's attributes (id, class, etc.)
                    # Store the heading's text and children
                    text_content = heading.text
                    children = list(heading)

                    # Clear the heading's text and children
                    heading.text = None
                    for child in children:
                        heading.remove(child)

                    # Set the anchor's text
                    if text_content:
                        anchor.text = text_content

                    # Add children to anchor, preserving their tail text
                    for child in children:
                        anchor.append(child)

                    # Add the anchor to the heading
                    heading.append(anchor)

        return None  # Modify root in place


class HeadingAnchorExtension(Extension):
    """
    Extension that wraps heading content in anchor links for headings with IDs.
    """

    def extendMarkdown(self, md: Any) -> None:
        """
        Register the heading anchor tree processor.
        """
        md.treeprocessors.register(HeadingAnchorTreeprocessor(md), "heading_anchor", 1)


def makeExtension(**kwargs: Any) -> Extension:
    """
    Factory function for the extension.

    This allows Python Markdown to load the extension by module name only
    (without specifying the class). For example:
        extensions=['wagtail_pdf_converter.markdown_extensions']

    Without this function, you must use the full dot notation with class name:
        extensions=['wagtail_pdf_converter.markdown_extensions:HeadingAnchorExtension']
    """
    return HeadingAnchorExtension(**kwargs)

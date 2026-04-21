import logging
import re
import time
import typing
import urllib.parse

from io import BytesIO
from typing import Any

import fitz  # PyMuPDF
import humanize

from bs4 import BeautifulSoup
from django.utils import timezone

from wagtail_pdf_converter.conf import settings as conf_settings

from .backends import get_ai_backend
from .image_processing import ImageProcessor


class DocumentLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds PDF converter context to all log messages."""

    def process(self, msg: Any, kwargs: typing.MutableMapping[str, Any]) -> tuple[Any, typing.MutableMapping[str, Any]]:
        extra = self.extra or {}
        doc_id = extra.get("document_id")
        if doc_id:
            return f"[Document {doc_id}] {msg}", kwargs
        return f"[PDF Converter] {msg}", kwargs


logger = DocumentLoggerAdapter(logging.getLogger(__name__), {"document_id": None})


class HybridPDFConverter:
    """
    A hybrid PDF converter that extracts images and converts content to markdown.

    This converter uses PyMuPDF for image extraction and processing, combined with
    AI backends for content analysis and markdown generation. It handles complex
    PDF structures including split images, masks, and various image formats.

    References:
    - PyMuPDF General Documentation: https://pymupdf.readthedocs.io/
    - PyMuPDF Image Recipes: https://pymupdf.readthedocs.io/en/latest/recipes-images.html
    """

    def __init__(
        self,
        max_workers: int = 5,
        batch_size: int = 10,
        backend_alias: str = "default",
    ) -> None:
        """Initialize the converter with AI backend and image processor."""
        self.ai_client = get_ai_backend(backend_alias)

        # Initialize components
        self.image_processor = ImageProcessor(
            max_workers=max_workers,
            batch_size=batch_size,
        )

    def split_pdf_into_chunks(self, pdf_bytes: bytes, pages_per_chunk: int, overlap_pages: int = 1) -> list[bytes]:
        """
        Splits a PDF into smaller PDF chunks with optional overlap.

        Args:
            pdf_bytes: The PDF content as bytes
            pages_per_chunk: Number of pages per chunk
            overlap_pages: Number of pages to overlap between chunks for context
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        chunks: list[bytes] = []

        start = 0
        while start < total_pages:
            end = min(start + pages_per_chunk, total_pages)

            # For chunks after the first, include overlap from previous chunk
            chunk_start = max(0, start - overlap_pages) if start > 0 else start

            chunk_doc = fitz.open()
            chunk_doc.insert_pdf(doc, from_page=chunk_start, to_page=end - 1)
            chunk_bytes = BytesIO()
            chunk_doc.save(chunk_bytes)
            chunks.append(chunk_bytes.getvalue())
            chunk_doc.close()

            start += pages_per_chunk

        doc.close()
        return chunks

    def _fix_hallucinated_links(self, markdown_content: str) -> str:
        """
        Fixes common hallucinated link patterns where the model creates a link
        but the URL is just a copy of the text or clearly invalid.
        """

        def replace_link(match: re.Match[str]) -> str:
            text = match.group(1)
            url = match.group(2)

            # Decode URL to compare with text
            try:
                decoded_url = urllib.parse.unquote(url)
            except Exception:
                decoded_url = url

            # Normalize both for comparison (remove spaces, lowercase, punctuation)
            # We want to catch cases like [Title](Title) or [Title](Title%20Text)
            norm_text = re.sub(r"[\s\-_]+", "", text.lower())
            norm_url = re.sub(r"[\s\-_]+", "", decoded_url.lower())

            # If URL is effectively the same as the text, it's likely a hallucination
            # e.g. [Guidance...](Guidance...)
            # Also check if the URL is just a fragment of the text
            if norm_text == norm_url or (len(norm_url) > 5 and norm_url in norm_text):
                # Check if it looks like a valid URL structure (http/https/www/mailto/tel)
                # or a relative path starting with / or # (anchors are fine)
                if not (
                    url.startswith("http")
                    or url.startswith("www")
                    or url.startswith("/")
                    or url.startswith("#")
                    or url.startswith("mailto:")
                    or url.startswith("tel:")
                ):
                    return text  # Return just the text, removing the link

            return match.group(0)  # Keep original

        # Regex to find markdown links: [text](url)
        # This handles balanced parentheses to some extent but simple regex is usually enough
        # for this specific cleanup task
        link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

        return link_pattern.sub(replace_link, markdown_content)

    def _post_process_chunked_markdown(self, markdown_content: str) -> str:
        """
        Post-processing to fix common chunking issues, especially with tables and lists.
        """
        # First, fix hallucinated links
        markdown_content = self._fix_hallucinated_links(markdown_content)

        # Compile regexes for performance
        merged_list_item_bullet_pattern = re.compile(r"^[a-zA-Z].*[a-z]\s*[-*]\s+")
        merged_list_item_bullet_split_pattern = re.compile(r"([-*]\s+)")
        merged_list_item_numbered_pattern = re.compile(r"^[a-zA-Z].*[a-z]\s*\d+\.\s+")
        merged_list_item_numbered_split_pattern = re.compile(r"(\d+\.\s+)")

        # Remove obvious AI conversational responses that may have leaked through.
        # This list is configurable via WAGTAIL_PDF_CONVERTER["CONVERSATIONAL_PHRASES"].
        conversational_phrases = conf_settings.CONVERSATIONAL_PHRASES

        lines = markdown_content.splitlines()
        processed_lines: list[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip lines that contain conversational AI responses
            if any(phrase in line.lower() for phrase in conversational_phrases):
                i += 1
                continue

            # Fix table rows that got merged with text
            if i > 0 and "|" in line and not line.strip().startswith("|"):
                # Find where the table starts
                table_start = line.find("|")
                if table_start > 0:
                    text_part = line[:table_start].strip()
                    table_part = line[table_start:].strip()
                    if text_part and processed_lines:
                        # Add text to previous line and start table on new line
                        processed_lines[-1] += " " + text_part
                        processed_lines.append("")
                        processed_lines.append(table_part)
                    else:
                        processed_lines.append(line)
                else:
                    processed_lines.append(line)

            # Fix list items that got merged with previous line
            # Regex explanation: ^[a-zA-Z].*[a-z]\s*[-*]\s+
            # - ^[a-zA-Z]: Line starts with a letter
            # - .*[a-z]: Contains text ending with a lowercase letter
            # - \s*: Optional whitespace
            # - [-*]\s+: Followed by a bullet point (- or *) and spaces
            # This catches cases like: "some text- First item" or "text * Item"
            elif i > 0 and merged_list_item_bullet_pattern.match(line):
                # Split on the bullet point marker, keeping the marker
                parts = merged_list_item_bullet_split_pattern.split(line, 1)
                if len(parts) >= 3 and processed_lines:
                    processed_lines[-1] += " " + parts[0]  # Add text to previous line
                    processed_lines.append("")  # Add blank line
                    processed_lines.append(parts[1] + parts[2])  # Add list item
                else:
                    processed_lines.append(line)

            # Fix numbered list items that got merged
            # Regex explanation: ^[a-zA-Z].*[a-z]\s*\d+\.\s+
            # - ^[a-zA-Z]: Line starts with a letter
            # - .*[a-z]: Contains text ending with a lowercase letter
            # - \s*: Optional whitespace
            # - \d+\.\s+: Followed by number(s), a period, and spaces
            # This catches cases like: "some text1. First item" or "text 2. Item"
            elif i > 0 and merged_list_item_numbered_pattern.match(line):
                # Split on the numbered list marker, keeping the marker
                parts = merged_list_item_numbered_split_pattern.split(line, 1)
                if len(parts) >= 3 and processed_lines:
                    processed_lines[-1] += " " + parts[0]
                    processed_lines.append("")
                    processed_lines.append(parts[1] + parts[2])
                else:
                    processed_lines.append(line)

            else:
                processed_lines.append(line)

            i += 1

        # Remove excessive blank lines (more than 2 consecutive)
        final_lines: list[str] = []
        blank_count = 0

        for line in processed_lines:
            if line.strip() == "":
                blank_count += 1
                if blank_count <= 2:  # Allow up to 2 consecutive blank lines
                    final_lines.append(line)
            else:
                blank_count = 0
                final_lines.append(line)

        return "\n".join(final_lines)

    def _make_anchor_ids_unique(self, markdown_content: str) -> str:
        """
        Ensures all anchor IDs in the given HTML/markdown content are unique.

        This function parses the content using BeautifulSoup, finds all elements
        with an 'id' attribute, and de-duplicates them by appending a suffix.
        It also updates the corresponding 'href' for self-linking anchor tags.

        Args:
            markdown_content: A string containing markdown with embedded HTML.

        Returns:
            The content with unique anchor IDs.
        """
        # We're using html.parser here, rather than html5lib because the latter
        # wraps fragments in <html><head></head><body>...</body></html> tags,
        # while html.parser adds minimal structure, which is important since we're
        # processing markdown that may contain mixed HTML/markdown content, and we
        # want to preserve whitespace and structure as much as possible.
        soup = BeautifulSoup(markdown_content, "html.parser")
        id_counts: dict[str, int] = {}

        # Find all tags that have an 'id' attribute
        for tag in soup.find_all(id=True):
            original_id = tag["id"]
            count = id_counts.get(original_id, 0)
            id_counts[original_id] = count + 1

            if count > 0:
                # This is a duplicate ID, so we need to make it unique
                new_id = f"{original_id}-{count}"
                tag["id"] = new_id

                # If it's a self-linking anchor, update the href as well
                if tag.name == "a" and tag.has_attr("href") and tag["href"] == f"#{original_id}":
                    tag["href"] = f"#{new_id}"

        # Convert the modified soup back to a string
        return str(soup)

    def _add_markdown_attributes_to_html(self, markdown_content: str) -> str:
        """
        Adds markdown="1" attribute to HTML block-level elements that don't have it.

        This is necessary for the md_in_html markdown extension to properly
        process markdown content inside HTML elements. Block-level elements like
        <blockquote>, <div>, <section>, etc. need this attribute to have their
        markdown content rendered.

        Args:
            markdown_content: A string containing markdown with embedded HTML.

        Returns:
            The content with markdown attributes added to HTML block elements.
        """
        # Block-level elements that commonly contain markdown content
        block_elements = [
            "blockquote",
            "div",
            "section",
            "article",
            "aside",
            "details",
            "figure",
            "figcaption",
            "footer",
            "header",
            "main",
            "nav",
            "ol",
            "ul",
            "li",
        ]

        soup = BeautifulSoup(markdown_content, "html.parser")

        # Find all block-level elements and add markdown="1" if not present
        for element_name in block_elements:
            for tag in soup.find_all(element_name):
                # Only add if the tag doesn't already have a markdown attribute
                if not tag.has_attr("markdown"):
                    tag["markdown"] = "1"

        return str(soup)

    def _remove_duplicate_content(self, markdown_parts: list[str]) -> list[str]:
        """
        Remove duplicate content from a list of markdown chunks generated with
        page overlap.

        The method iterates through the chunks, comparing the beginning of each new
        chunk with the end of the previously processed content. It identifies the
        extent of the overlap by checking if segments from the start of the current
        chunk are present at the end of the previous one. Once the overlap is
        found, it's removed from the current chunk before appending it to the
        results. This ensures a seamless join between chunks without repetitive
        text.
        """
        if len(markdown_parts) <= 1:
            return markdown_parts

        cleaned_parts = [markdown_parts[0]]  # First chunk is always kept as-is

        for i in range(1, len(markdown_parts)):
            current_chunk = markdown_parts[i]
            previous_chunk = cleaned_parts[-1]

            # Split current chunk into lines for comparison
            current_lines = current_chunk.strip().splitlines()

            # Find overlapping content by comparing the end of previous chunk
            # with the beginning of current chunk
            overlap_found = False
            overlap_end = 0

            # Look for overlap in the first 20 lines of current chunk
            for j in range(min(20, len(current_lines))):
                current_segment = "\n".join(current_lines[: j + 1]).strip()
                if current_segment and current_segment in previous_chunk:
                    overlap_end = j + 1
                    overlap_found = True

            if overlap_found and overlap_end > 0:
                # Remove the overlapping part from current chunk
                cleaned_current = "\n".join(current_lines[overlap_end:])
                if cleaned_current.strip():
                    cleaned_parts.append(cleaned_current)
            else:
                cleaned_parts.append(current_chunk)

        return cleaned_parts

    def convert_pdf_to_markdown(
        self,
        pdf_bytes: bytes,
        collection_name: str,
        document_id: int | None = None,
        force_chunking: bool = False,
        pages_per_chunk: int = 15,
    ) -> tuple[str, dict[str, Any]]:
        """Orchestrates the full PDF to Markdown conversion process."""

        # Create logger with document_id for this conversion
        logger = DocumentLoggerAdapter(logging.getLogger(__name__), {"document_id": document_id})

        metrics: dict[str, Any] = {}
        start_time = time.time()

        try:
            page_count = fitz.open(stream=pdf_bytes, filetype="pdf").page_count
        except Exception:
            page_count = 0

        metrics.update(
            {
                "pdf_size": humanize.naturalsize(len(pdf_bytes)),
                "total_pages": page_count,
            }
        )

        # Extract images, get descriptions, upload them, but keep original PDF intact
        image_report_list, images_processed = self.image_processor.extract_and_upload_images(
            pdf_bytes, collection_name, self.ai_client
        )

        metrics["images_processed"] = images_processed

        logger.info(
            "Generated image report with %d meaningful images, requesting markdown conversion from Gemini",
            len(image_report_list),
        )

        # Use original PDF (with images intact) + image report
        prompt = self.ai_client.format_image_report_and_get_prompt(image_report_list)

        chunk_threshold = conf_settings.CHUNK_PAGE_THRESHOLD

        if force_chunking or page_count > chunk_threshold:
            metrics["processing_method"] = f"Chunked ({pages_per_chunk} pages/chunk)"
            logger.info("Splitting PDF into chunks of %d pages", pages_per_chunk)
            chunks = self.split_pdf_into_chunks(
                pdf_bytes, pages_per_chunk, overlap_pages=1
            )  # Use original PDF with 1-page overlap
            markdown_parts: list[str] = []
            previous_chunk_markdown: str | None = None
            for i, chunk_bytes in enumerate(chunks, 1):
                logger.info("Converting chunk %d/%d", i, len(chunks))
                try:
                    markdown_chunk = self.ai_client.convert_chunk_with_continuation(
                        chunk_bytes=chunk_bytes,
                        base_prompt=prompt,
                        previous_chunk_markdown=previous_chunk_markdown,
                        chunk_number=i,
                        total_chunks=len(chunks),
                    )
                    markdown_parts.append(markdown_chunk)
                    previous_chunk_markdown = markdown_chunk

                except Exception as e:
                    logger.error("Failed to convert chunk %d after all retries: %s", i, e)
                    markdown_parts.append(f"\n\n--- ERROR CONVERTING CHUNK {i} ---\n\n")

            # Remove duplicate content from overlapping chunks
            cleaned_parts = self._remove_duplicate_content(markdown_parts)
            markdown_content = self._post_process_chunked_markdown("\n\n".join(cleaned_parts))
            markdown_content = self._make_anchor_ids_unique(markdown_content)
            markdown_content = self._add_markdown_attributes_to_html(markdown_content)
        else:
            metrics["processing_method"] = "Single Pass"
            markdown_content = self.ai_client.convert_single_pass(pdf_bytes, prompt)
            markdown_content = self._add_markdown_attributes_to_html(markdown_content)

        # Calculate final metrics
        total_time = time.time() - start_time
        metrics["total_processing_time"] = f"{total_time:.2f} seconds"
        metrics["markdown_output_size"] = humanize.naturalsize(len(markdown_content.encode("utf-8")))
        metrics["converted_at"] = timezone.now().isoformat()

        logger.info(
            "Conversion complete - Method: %s, Time: %s, Pages: %s, Size: %s, Images: %s",
            metrics["processing_method"],
            metrics["total_processing_time"],
            metrics["total_pages"],
            metrics["pdf_size"],
            metrics["images_processed"],
        )

        return markdown_content, metrics

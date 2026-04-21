from unittest import mock

import factory

from django.test import SimpleTestCase, override_settings
from google.genai import errors as google_genai_errors
from tenacity import RetryError, stop_after_attempt, wait_none

from wagtail_pdf_converter import services
from wagtail_pdf_converter.services import backends, image_processing


class TestImageHandling(SimpleTestCase):
    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    def setUp(self):
        self.converter = services.HybridPDFConverter()
        self.ai_client = self.converter.ai_client
        self.image_processor = self.converter.image_processor
        self.test_image_bytes = factory.django.ImageField()._make_data({"width": 100, "height": 100, "format": "PNG"})

    @mock.patch("google.genai.Client")
    def test_describe_single_image_meaningful(self, mock_client):
        mock_response = mock.Mock()
        mock_response.text = "MEANINGFUL: A black square."
        mock_generate_content = mock.Mock(return_value=mock_response)
        self.ai_client.client.models.generate_content = mock_generate_content

        description = self.ai_client.describe_single_image(self.test_image_bytes, "png", 1, 0)
        self.assertEqual(description, "A black square.")
        mock_generate_content.assert_called_once()

    @mock.patch("google.genai.Client")
    def test_describe_single_image_decorative(self, mock_client):
        mock_response = mock.Mock()
        mock_response.text = "DECORATIVE"
        mock_generate_content = mock.Mock(return_value=mock_response)
        self.ai_client.client.models.generate_content = mock_generate_content

        description = self.ai_client.describe_single_image(self.test_image_bytes, "png", 1, 0)
        self.assertEqual(description, "DECORATIVE")

    @mock.patch("google.genai.Client")
    def test_describe_images_batch_success(self, mock_client):
        mock_response = mock.Mock()
        mock_response.text = "MEANINGFUL: Image 1.---SEPARATOR---DECORATIVE"
        mock_generate_content = mock.Mock(return_value=mock_response)
        self.ai_client.client.models.generate_content = mock_generate_content

        image_batch = [
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 0,
            },
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 1,
            },
        ]
        descriptions = self.ai_client.describe_images_batch(image_batch)
        self.assertEqual(descriptions, ["Image 1.", "DECORATIVE"])

    @mock.patch("google.genai.Client")
    def test_describe_images_batch_fallback(self, mock_client):
        # Simulate batch failure (wrong number of descriptions)
        mock_response = mock.Mock()
        mock_response.text = "A single description"
        mock_generate_content = mock.Mock(return_value=mock_response)
        self.ai_client.client.models.generate_content = mock_generate_content

        image_batch = [
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 0,
            },
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 1,
            },
        ]

        with mock.patch.object(self.ai_client, "_describe_images_individually") as mock_fallback:
            mock_fallback.return_value = ["Desc 1", "Desc 2"]
            descriptions = self.ai_client.describe_images_batch(image_batch)
            mock_fallback.assert_called_once_with(image_batch)
            self.assertEqual(descriptions, ["Desc 1", "Desc 2"])

    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    def test_process_image_batch(self, mock_add_image):
        mock_add_image.return_value = "/media/images/test.png"
        image_batch = [
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 0,
            },
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 1,
            },
        ]
        descriptions = ["A test image.", "DECORATIVE"]

        with mock.patch.object(self.ai_client, "describe_images_batch", return_value=descriptions):
            results = self.image_processor.process_image_batch(image_batch, "test-collection", self.ai_client)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["description"], "A test image.")
            self.assertEqual(results[0]["url"], "/media/images/test.png")
            mock_add_image.assert_called_once()  # Called only for the non-decorative image

    def test_format_image_report(self):
        image_report_list = [
            {"page": 1, "description": "Desc 1", "url": "/url/1"},
            {"page": 2, "description": "Desc 2", "url": "/url/2"},
        ]
        report_text = self.ai_client._format_image_report(image_report_list)
        self.assertIn("EXTRACTED IMAGES:", report_text)
        self.assertIn("- Page 1: Desc 1", report_text)
        self.assertIn("  URL: /url/1", report_text)
        self.assertIn("- Page 2: Desc 2", report_text)
        self.assertIn("  URL: /url/2", report_text)

    def test_format_image_report_empty(self):
        report_text = self.ai_client._format_image_report([])
        self.assertEqual(report_text, "No images were found in this document.")


class TestPDFChunking(SimpleTestCase):
    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    def setUp(self):
        self.converter = services.HybridPDFConverter()
        self.ai_client = self.converter.ai_client

    @mock.patch(services.converter.__name__ + ".fitz")
    def test_split_pdf_into_chunks(self, mock_fitz):
        # Create a mock PDF with 10 pages
        mock_doc = mock.MagicMock()
        mock_doc.page_count = 10
        mock_doc.__len__.return_value = 10
        mock_fitz.open.return_value = mock_doc

        # Mock the chunk saving
        mock_chunk_doc = mock.MagicMock()
        # Original doc, then 3 chunks
        mock_fitz.open.side_effect = [
            mock_doc,
            mock_chunk_doc,
            mock_chunk_doc,
            mock_chunk_doc,
        ]

        pdf_bytes = b"a fake pdf"
        chunks = self.converter.split_pdf_into_chunks(pdf_bytes, pages_per_chunk=4)

        self.assertEqual(len(chunks), 3)  # 10 pages / 4 per chunk = 3 chunks
        self.assertEqual(mock_chunk_doc.insert_pdf.call_count, 3)
        # With 1-page overlap:
        # Chunk 1: pages 0-3 (no overlap for first chunk)
        # Chunk 2: pages 3-7 (starts 1 page earlier due to overlap)
        # Chunk 3: pages 7-9 (starts 1 page earlier due to overlap)
        mock_chunk_doc.insert_pdf.assert_any_call(mock_doc, from_page=0, to_page=3)
        mock_chunk_doc.insert_pdf.assert_any_call(mock_doc, from_page=3, to_page=7)
        mock_chunk_doc.insert_pdf.assert_any_call(mock_doc, from_page=7, to_page=9)

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    @mock.patch(image_processing.__name__ + ".fitz")  # Mock fitz in image_processing
    @mock.patch(services.converter.__name__ + ".fitz")  # Mock fitz in converter
    @mock.patch("google.genai.Client")
    def test_conversion_with_chunking(self, mock_client, mock_fitz_converter, mock_fitz_img, mock_add_image):
        # Mock document for both converter and image processing
        mock_doc = mock.MagicMock()
        mock_doc.page_count = 20
        mock_doc.__len__.return_value = 20
        mock_doc.__iter__ = mock.Mock(return_value=iter([]))

        # Both fitz mocks should return the same mock document
        mock_fitz_converter.open.return_value = mock_doc
        mock_fitz_img.open.return_value = mock_doc

        converter = services.HybridPDFConverter()
        pdf_bytes = b"large pdf"

        with (
            mock.patch.object(converter, "split_pdf_into_chunks") as mock_split,
            mock.patch.object(converter.ai_client, "convert_chunk_with_continuation") as mock_convert,
        ):
            mock_split.return_value = [b"chunk1", b"chunk2"]
            mock_convert.side_effect = ["Markdown 1", "Markdown 2"]

            markdown_content, metrics = converter.convert_pdf_to_markdown(
                pdf_bytes, "test-collection", force_chunking=True, pages_per_chunk=10
            )

            mock_split.assert_called_once_with(pdf_bytes, 10, overlap_pages=1)
            self.assertEqual(mock_convert.call_count, 2)
            self.assertEqual(markdown_content, "Markdown 1\n\nMarkdown 2")
            self.assertIn("Chunked", metrics["processing_method"])

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    @mock.patch(image_processing.__name__ + ".fitz")
    @mock.patch(services.converter.__name__ + ".fitz")
    @mock.patch("google.genai.Client")
    def test_conversion_chunk_failure_inserts_error_and_continues(
        self, mock_client, mock_fitz_converter, mock_fitz_img, mock_add_image
    ):
        """Test that when a chunk conversion fails, error message is inserted and processing continues."""
        mock_doc = mock.MagicMock()
        mock_doc.page_count = 30
        mock_doc.__len__.return_value = 30
        mock_doc.__iter__ = mock.Mock(return_value=iter([]))

        mock_fitz_converter.open.return_value = mock_doc
        mock_fitz_img.open.return_value = mock_doc

        converter = services.HybridPDFConverter()
        pdf_bytes = b"large pdf"

        with (
            mock.patch.object(converter, "split_pdf_into_chunks") as mock_split,
            mock.patch.object(converter.ai_client, "convert_chunk_with_continuation") as mock_convert,
        ):
            # Chunk 2 fails with an API error
            mock_split.return_value = [b"chunk1", b"chunk2", b"chunk3"]
            mock_convert.side_effect = [
                "Markdown from chunk 1",
                Exception("API timeout on chunk 2"),
                "Markdown from chunk 3",
            ]

            markdown_content, metrics = converter.convert_pdf_to_markdown(
                pdf_bytes, "test-collection", force_chunking=True, pages_per_chunk=10
            )

            # All 3 chunks should be attempted
            self.assertEqual(mock_convert.call_count, 3)
            # Result should contain content from chunks 1 and 3, plus error message for chunk 2
            self.assertIn("Markdown from chunk 1", markdown_content)
            self.assertIn("ERROR CONVERTING CHUNK 2", markdown_content)
            self.assertIn("Markdown from chunk 3", markdown_content)

    def test_convert_chunk_with_continuation_with_previous_markdown(self):
        """
        Test that convert_chunk_with_continuation includes the previous
        markdown in the prompt.
        """
        chunk_bytes = b"pdf content"
        base_prompt = "base prompt"
        previous_chunk_markdown = "line 1\nline 2\nline 3\nline 4\nline 5\nline 6"

        with mock.patch.object(self.ai_client, "convert_content_with_retry") as mock_convert:
            self.ai_client.convert_chunk_with_continuation(
                chunk_bytes,
                base_prompt,
                previous_chunk_markdown,
                chunk_number=2,
                total_chunks=3,
            )

            # Check that the generate_content method was called with the correct prompt
            args, kwargs = mock_convert.call_args
            sent_contents = args[0]

            # The continuation prompt should contain chunk info and previous markdown context
            continuation_prompt_found = False
            for content in sent_contents:
                if isinstance(content, str) and "chunk 2 of 3" in content:
                    continuation_prompt_found = True
                    # Check that it contains some of the previous markdown context
                    self.assertIn("line", content)  # Should contain lines from previous chunk
                    break

            self.assertTrue(
                continuation_prompt_found,
                "Continuation prompt with chunk info not found",
            )
            self.assertIn(base_prompt, sent_contents)

    def test_convert_chunk_with_continuation_without_previous_markdown(self):
        """
        Test that convert_chunk_with_continuation does not include the
        continuation prompt when there is no previous markdown.
        """
        chunk_bytes = b"pdf content"
        base_prompt = "base prompt"

        with mock.patch.object(self.ai_client, "convert_content_with_retry") as mock_convert:
            self.ai_client.convert_chunk_with_continuation(
                chunk_bytes, base_prompt, None, chunk_number=1, total_chunks=1
            )

            args, kwargs = mock_convert.call_args
            sent_contents = args[0]

            # Check that no continuation prompt is in the contents
            has_continuation = any(isinstance(content, str) and "chunk" in content.lower() for content in sent_contents)
            self.assertFalse(has_continuation, "Continuation prompt found when it shouldn't be")
            self.assertIn(base_prompt, sent_contents)


class TestPDFConverter(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Update the retry policy on the AIClient method
        cls._retry_obj = (
            backends.gemini.GeminiBackend.convert_content_with_retry.retry  # type: ignore[attr-defined]
        )
        cls._old_wait = cls._retry_obj.wait
        cls._old_stop = cls._retry_obj.stop
        cls._retry_obj.wait = wait_none()
        cls._retry_obj.stop = stop_after_attempt(1)

    @classmethod
    def tearDownClass(cls):
        # Restore original retry policy
        cls._retry_obj.wait = cls._old_wait
        cls._retry_obj.stop = cls._old_stop
        super().tearDownClass()

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": ""},
                }
            }
        }
    )
    def test_missing_api_key_raises_error(self):
        with self.assertRaisesMessage(
            services.PDFConversionError,
            "API key must be provided in backend configuration.",
        ):
            services.HybridPDFConverter()

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    @mock.patch(image_processing.__name__ + ".fitz")
    @mock.patch("google.genai.Client")
    @mock.patch(backends.gemini.__name__ + ".wait_exponential", return_value=wait_none())
    def test_conversion_successful(self, mock_wait, mock_client, mock_fitz, mock_add_image):
        # Mock PyMuPDF document
        mock_doc = mock.Mock()
        mock_doc.page_count = 1
        mock_doc.__iter__ = mock.Mock(return_value=iter([]))
        mock_fitz.open.return_value = mock_doc

        mock_response = mock.Mock()
        mock_response.text = "## Test Markdown"
        mock_generate_content = mock.Mock(return_value=mock_response)
        mock_client.return_value.models.generate_content = mock_generate_content

        converter = services.HybridPDFConverter()
        pdf_bytes = b"test pdf content"
        markdown_content, metrics = converter.convert_pdf_to_markdown(pdf_bytes, "test-collection")

        self.assertEqual(markdown_content, "## Test Markdown")
        self.assertIn("total_processing_time", metrics)

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    @mock.patch(image_processing.__name__ + ".fitz")
    @mock.patch("google.genai.Client")
    @mock.patch(backends.gemini.__name__ + ".wait_exponential", return_value=wait_none())
    def test_api_error_raises_conversion_error(self, mock_wait, mock_client, mock_fitz, mock_add_image):
        # Mock PyMuPDF document
        mock_doc = mock.Mock()
        mock_doc.page_count = 1
        mock_doc.__iter__ = mock.Mock(return_value=iter([]))
        mock_fitz.open.return_value = mock_doc

        mock_generate_content = mock.Mock(side_effect=Exception("API Error"))
        mock_client.return_value.models.generate_content = mock_generate_content

        converter = services.HybridPDFConverter()
        pdf_bytes = b"test pdf content"

        with self.assertRaises(RetryError):
            converter.convert_pdf_to_markdown(pdf_bytes, "test-collection")

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    @mock.patch(image_processing.__name__ + ".fitz")
    @mock.patch("google.genai.Client")
    @mock.patch(backends.gemini.__name__ + ".wait_exponential", return_value=wait_none())
    def test_no_text_in_response_raises_conversion_error(self, mock_wait, mock_client, mock_fitz, mock_add_image):
        # Mock PyMuPDF document
        mock_doc = mock.Mock()
        mock_doc.page_count = 1
        mock_doc.__iter__ = mock.Mock(return_value=iter([]))
        mock_fitz.open.return_value = mock_doc

        mock_response = mock.Mock()
        mock_response.text = ""
        mock_response.prompt_feedback = None
        mock_generate_content = mock.Mock(return_value=mock_response)
        mock_client.return_value.models.generate_content = mock_generate_content

        converter = services.HybridPDFConverter()
        pdf_bytes = b"test pdf content"

        with self.assertRaises(RetryError):
            converter.convert_pdf_to_markdown(pdf_bytes, "test-collection")

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch("google.genai.Client")
    @mock.patch(backends.gemini.__name__ + ".wait_exponential", return_value=wait_none())
    def test_server_error_503_triggers_retry(self, mock_wait, mock_client):
        """Test that ServerError (503 Service Unavailable) triggers retry mechanism."""
        server_error = google_genai_errors.ServerError(
            503,
            {
                "error": {
                    "code": 503,
                    "message": "The model is overloaded. Please try again later.",
                    "status": "UNAVAILABLE",
                }
            },
            None,
        )

        mock_generate_content = mock.Mock(side_effect=server_error)
        mock_client.return_value.models.generate_content = mock_generate_content

        converter = services.HybridPDFConverter()

        # Should exhaust retries and raise RetryError
        with self.assertRaises(RetryError) as context:
            converter.ai_client.convert_content_with_retry(["test content"])

        # Verify the original exception is ServerError
        self.assertIsInstance(context.exception.last_attempt.exception(), google_genai_errors.ServerError)

        # Verify it attempted to call the API
        # (with our test setup of stop_after_attempt(1), it should be called once)
        self.assertEqual(mock_generate_content.call_count, 1)

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    @mock.patch("google.genai.Client")
    def test_prompt_contains_numbered_section_instructions(self, mock_client):
        converter = services.HybridPDFConverter()
        prompt = converter.ai_client._get_prompt("Test image report")

        # Verify the prompt contains instructions for numbered sections
        self.assertIn("Numbered Sections and Paragraphs for Web Linking", prompt)
        self.assertIn("paragraph-N", prompt)
        self.assertIn("section-N", prompt)
        self.assertIn('id="paragraph-1"', prompt)
        self.assertIn("#section-2-1", prompt)

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    def test_make_anchor_ids_unique(self):
        converter = services.HybridPDFConverter()
        markdown_content = (
            '<a id="paragraph-1" href="#paragraph-1">Content</a>\n'
            '<h2 id="section-1">Section One</h2>\n'
            '<a id="paragraph-1" href="#paragraph-1">More content</a>\n'
            '<h3 id="section-1">Subsection One</h3>'
        )
        expected_content = (
            '<a href="#paragraph-1" id="paragraph-1">Content</a>\n'
            '<h2 id="section-1">Section One</h2>\n'
            '<a href="#paragraph-1-1" id="paragraph-1-1">More content</a>\n'
            '<h3 id="section-1-1">Subsection One</h3>'
        )
        processed_content = converter._make_anchor_ids_unique(markdown_content)
        self.assertEqual(processed_content, expected_content)


class TestMarkdownAttributeFixer(SimpleTestCase):
    """Tests for adding markdown="1" attribute to HTML block elements."""

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    def setUp(self):
        self.converter = services.HybridPDFConverter()

    def test_adds_markdown_attribute_to_blockquote(self):
        """Test that markdown="1" is added to blockquote elements."""
        markdown_content = (
            '<blockquote class="summary-of-requirements">\n'
            "**Summary of requirements**\n\n"
            '<a class="section__global-number" href="#paragraph-3-14" id="paragraph-3-14">3.14</a>'
            "Some content with *italic* text.\n\n"
            "* List item 1\n"
            "* List item 2\n"
            "</blockquote>"
        )
        expected_output = (
            '<blockquote class="summary-of-requirements" markdown="1">\n'
            "**Summary of requirements**\n\n"
            '<a class="section__global-number" href="#paragraph-3-14" id="paragraph-3-14">3.14</a>'
            "Some content with *italic* text.\n\n"
            "* List item 1\n"
            "* List item 2\n"
            "</blockquote>"
        )
        result = self.converter._add_markdown_attributes_to_html(markdown_content)
        self.assertEqual(result, expected_output)

    def test_adds_markdown_attribute_to_div(self):
        """Test that markdown="1" is added to div elements."""
        markdown_content = '<div class="info">\n## Heading\n\nParagraph with **bold**.\n</div>'
        expected_output = '<div class="info" markdown="1">\n## Heading\n\nParagraph with **bold**.\n</div>'
        result = self.converter._add_markdown_attributes_to_html(markdown_content)
        self.assertEqual(result, expected_output)

    def test_adds_markdown_attribute_to_element_without_attributes(self):
        """Test that markdown="1" is added to elements without existing attributes."""
        markdown_content = "<blockquote>\nSome **markdown** content.\n</blockquote>"
        expected_output = '<blockquote markdown="1">\nSome **markdown** content.\n</blockquote>'
        result = self.converter._add_markdown_attributes_to_html(markdown_content)
        self.assertEqual(result, expected_output)

    def test_skips_elements_that_already_have_markdown_attribute(self):
        """Test that elements with markdown attribute are not modified."""
        markdown_content = '<blockquote class="test" markdown="1">\nContent here.\n</blockquote>'
        # Should remain unchanged
        result = self.converter._add_markdown_attributes_to_html(markdown_content)
        self.assertEqual(result, markdown_content)

    def test_handles_multiple_elements(self):
        """Test that multiple elements are processed correctly."""
        markdown_content = (
            '<blockquote class="note">\n**Note:** Important.\n</blockquote>\n\n'
            '<div class="warning">\n*Warning:* Be careful.\n</div>\n\n'
            '<section id="intro">\n## Introduction\n</section>'
        )
        # Note: bs4 will normalise whitespace, collapsing the double newlines into a single newline
        expected_output = (
            '<blockquote class="note" markdown="1">\n**Note:** Important.\n</blockquote>\n'
            '<div class="warning" markdown="1">\n*Warning:* Be careful.\n</div>\n'
            '<section id="intro" markdown="1">\n## Introduction\n</section>'
        )
        result = self.converter._add_markdown_attributes_to_html(markdown_content)
        self.assertEqual(result, expected_output)

    def test_does_not_affect_inline_elements(self):
        """Test that inline elements are not affected."""
        markdown_content = (
            'Some text with <span class="highlight">**bold**</span> content.\n<a href="#section">Link</a> here.'
        )
        # Should remain unchanged (`span` and `a` are not in the block_elements list)
        result = self.converter._add_markdown_attributes_to_html(markdown_content)
        self.assertEqual(result, markdown_content)

    def test_handles_empty_content(self):
        """Test that empty content is handled gracefully."""
        markdown_content = ""
        result = self.converter._add_markdown_attributes_to_html(markdown_content)
        self.assertEqual(result, "")

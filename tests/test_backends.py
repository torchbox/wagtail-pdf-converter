from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from wagtail_pdf_converter.services.backends import AIPDFBackend, get_ai_backend
from wagtail_pdf_converter.services.backends.gemini import GeminiBackend


class MockBackend(AIPDFBackend):
    def __init__(self, config):
        self.config = config

    def describe_images_batch(self, image_batch):
        return []

    def describe_single_image(self, image_bytes, image_format, page_num, img_index):
        return ""

    def format_image_report_and_get_prompt(self, image_report):
        return ""

    def convert_content_with_retry(self, contents):
        return ""

    def convert_chunk_with_continuation(
        self,
        chunk_bytes: bytes,
        base_prompt: str,
        previous_chunk_markdown: str | None = None,
        chunk_number: int = 1,
        total_chunks: int = 1,
    ):
        return ""

    def convert_single_pass(self, pdf_bytes, prompt):
        return ""


class TestBackendLoader(SimpleTestCase):
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
    def test_get_default_backend(self):
        backend = get_ai_backend("default")
        self.assertIsInstance(backend, GeminiBackend)

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {"mock": {"CLASS": "tests.test_backends.MockBackend", "CONFIG": {"foo": "bar"}}}
        }
    )
    def test_get_custom_backend(self):
        backend = get_ai_backend("mock")
        self.assertIsInstance(backend, MockBackend)
        self.assertEqual(backend.config, {"foo": "bar"})

    def test_invalid_alias_raises_error(self):
        with self.assertRaises(ImproperlyConfigured):
            get_ai_backend("nonexistent")

    @override_settings(WAGTAIL_PDF_CONVERTER={"AI_BACKENDS": {"invalid": {"CONFIG": {}}}})
    def test_missing_class_raises_error(self):
        with self.assertRaises(ImproperlyConfigured):
            get_ai_backend("invalid")

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "invalid": {
                    "CLASS": "nonexistent.module.Class",
                }
            }
        }
    )
    def test_import_error_raises_error(self):
        with self.assertRaises(ImproperlyConfigured):
            get_ai_backend("invalid")

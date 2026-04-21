from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from django.utils.timezone import now

from wagtail_pdf_converter.conf import DEFAULTS, PDFConverterSettings, perform_import


class TestPDFConverterSettings(SimpleTestCase):
    def setUp(self):
        self.settings = PDFConverterSettings()

    def test_defaults(self):
        """Unmodified settings return the documented default values."""
        self.assertEqual(self.settings.AI_BACKENDS["default"]["CONFIG"]["IMAGE_MODEL"], "gemini-2.5-flash")
        self.assertEqual(self.settings.PDF_CONVERSION_TIMEOUT_HOURS, 3)
        self.assertIs(self.settings.AUTO_CONVERT_PDFS, False)
        self.assertEqual(
            self.settings.DOCUMENT_CONVERSION_QUERY_HELPER.__name__,
            "DocumentConversionQueryHelper",
        )

    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"IMAGE_MODEL": "custom-model"},
                }
            }
        }
    )
    def test_user_settings_override(self):
        """A user-supplied value replaces the default for that key."""
        settings = PDFConverterSettings()
        self.assertEqual(settings.AI_BACKENDS["default"]["CONFIG"]["IMAGE_MODEL"], "custom-model")
        # Other defaults are still available
        self.assertEqual(settings.PDF_CONVERSION_TIMEOUT_HOURS, 3)

    @override_settings(WAGTAIL_PDF_CONVERTER={"PROMPTS": {"PDF_CONVERSION_TEMPLATE": "my prompt"}})
    def test_partial_prompts_override_merges_with_defaults(self):
        """Overriding a single PROMPTS key does not erase other default prompts."""
        settings = PDFConverterSettings()
        self.assertEqual(settings.PROMPTS["PDF_CONVERSION_TEMPLATE"], "my prompt")
        # Unoverridden keys should keep their default values
        self.assertEqual(
            settings.PROMPTS["IMAGE_DESCRIPTION_TEMPLATE"],
            DEFAULTS["PROMPTS"]["IMAGE_DESCRIPTION_TEMPLATE"],
        )

    def test_unknown_setting_raises_attribute_error(self):
        """Accessing a key not in DEFAULTS raises AttributeError."""
        with self.assertRaises(AttributeError):
            _ = self.settings.NON_EXISTENT_SETTING

    @override_settings(WAGTAIL_PDF_CONVERTER={"NEW_SETTING": "value"})
    def test_unknown_user_setting_still_raises_attribute_error(self):
        """Keys present in WAGTAIL_PDF_CONVERTER but absent from DEFAULTS are not exposed."""
        settings = PDFConverterSettings()
        with self.assertRaises(AttributeError):
            _ = settings.NEW_SETTING

    def test_init_with_explicit_user_settings(self):
        """PDFConverterSettings can be constructed with explicit user_settings."""
        settings = PDFConverterSettings(
            user_settings={"AI_BACKENDS": {"default": {"CLASS": "...", "CONFIG": {"IMAGE_MODEL": "direct"}}}}
        )
        self.assertEqual(settings.AI_BACKENDS["default"]["CONFIG"]["IMAGE_MODEL"], "direct")

    def test_reload_clears_cached_values(self):
        """reload() purges the attribute cache so subsequent reads get fresh values."""
        settings = PDFConverterSettings()
        _ = settings.AI_BACKENDS  # populate cache
        self.assertIn("AI_BACKENDS", settings._cached_attrs)
        settings.reload()
        self.assertNotIn("AI_BACKENDS", settings._cached_attrs)
        self.assertFalse(hasattr(settings, "_user_settings"))

    def test_cached_value_is_returned_on_subsequent_access(self):
        """A value is cached after the first read and returned directly thereafter."""
        settings = PDFConverterSettings()
        val1 = settings.AI_BACKENDS
        val2 = settings.AI_BACKENDS  # second access hits __dict__, not __getattr__
        self.assertEqual(val1, val2)


class TestPerformImport(SimpleTestCase):
    def test_none_returns_none(self):
        """perform_import(None, ...) returns None without raising."""
        self.assertIsNone(perform_import(None, "SOME_SETTING"))

    def test_string_is_imported(self):
        """A dotted-path string is imported and the resulting object returned."""
        result = perform_import("django.utils.timezone.now", "SOME_SETTING")
        self.assertIs(result, now)

    def test_list_of_strings_are_imported(self):
        """A list of dotted-path strings is imported and returned as a list of objects."""

        result = perform_import(
            ["django.utils.timezone.now", "django.utils.timezone.now"],
            "SOME_SETTING",
        )
        self.assertEqual(result, [now, now])

    def test_non_string_passthrough(self):
        """A non-string, non-list value is returned unchanged."""
        self.assertEqual(perform_import(42, "SOME_SETTING"), 42)


class TestConversionStatusDisplaySetting(SimpleTestCase):
    def test_default_is_none(self):
        """CONVERSION_STATUS_DISPLAY defaults to None (show in both views)."""
        s = PDFConverterSettings()
        self.assertIsNone(s.CONVERSION_STATUS_DISPLAY)

    @override_settings(WAGTAIL_PDF_CONVERTER={"CONVERSION_STATUS_DISPLAY": "index_view"})
    def test_accepts_index_view(self):
        s = PDFConverterSettings()
        self.assertEqual(s.CONVERSION_STATUS_DISPLAY, "index_view")

    @override_settings(WAGTAIL_PDF_CONVERTER={"CONVERSION_STATUS_DISPLAY": "edit_view"})
    def test_accepts_edit_view(self):
        s = PDFConverterSettings()
        self.assertEqual(s.CONVERSION_STATUS_DISPLAY, "edit_view")

    @override_settings(WAGTAIL_PDF_CONVERTER={"CONVERSION_STATUS_DISPLAY": "listing"})
    def test_invalid_value_raises_improperly_configured(self):
        """A value that is not 'index_view' or 'edit_view' raises ImproperlyConfigured."""
        s = PDFConverterSettings()
        with self.assertRaises(ImproperlyConfigured):
            _ = s.CONVERSION_STATUS_DISPLAY

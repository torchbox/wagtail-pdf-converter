from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.utils.module_loading import import_string

from . import constants, prompts


DEFAULTS = {
    "AUTO_CONVERT_PDFS": False,
    "PDF_CONVERSION_TIMEOUT_HOURS": 3,
    "EXTRACTED_IMAGES_COLLECTION_NAME": constants.EXTRACTED_IMAGES_COLLECTION_NAME,
    "CHUNK_PAGE_THRESHOLD": constants.PDF_CONVERTER_CHUNK_PAGE_THRESHOLD_DEFAULT,
    "PROMPTS": {
        "IMAGE_DESCRIPTION_TEMPLATE": prompts.DEFAULT_IMAGE_DESCRIPTION_PROMPT_TEMPLATE,
        "SINGLE_IMAGE_OUTPUT_INSTRUCTIONS": prompts.DEFAULT_SINGLE_IMAGE_OUTPUT_INSTRUCTIONS,
        "BATCH_IMAGE_OUTPUT_INSTRUCTIONS": prompts.DEFAULT_BATCH_IMAGE_OUTPUT_INSTRUCTIONS,
        "IMAGE_SINGLE_DESCRIPTION": prompts.DEFAULT_IMAGE_SINGLE_DESCRIPTION_PROMPT,
        "IMAGE_BATCH_DESCRIPTION": prompts.DEFAULT_IMAGE_BATCH_DESCRIPTION_PROMPT,
        "PDF_CONVERSION_TEMPLATE": prompts.DEFAULT_PDF_CONVERSION_PROMPT_TEMPLATE,
        "MARKDOWN_CONTINUATION": prompts.DEFAULT_MARKDOWN_CONTINUATION_PROMPT,
    },
    "CONVERSATIONAL_PHRASES": prompts.DEFAULT_CONVERSATIONAL_PHRASES,
    "ENABLE_ADMIN_EXTENSIONS": False,
    "BASE_TEMPLATE": "wagtail_pdf_converter/base.html",
    # None means show status in both index and edit views.
    # Set to ConversionStatusDisplay.INDEX_VIEW or EDIT_VIEW to restrict to one.
    "CONVERSION_STATUS_DISPLAY": None,
    "FILTER_PDF_IMAGES": True,
    "DOCUMENT_CONVERSION_QUERY_HELPER": "wagtail_pdf_converter.utils.DocumentConversionQueryHelper",
    "AI_BACKENDS": {
        "default": {
            "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
            "CONFIG": {
                "API_KEY": "",
                "IMAGE_MODEL": "gemini-2.5-flash",
                "CONVERSION_MODEL": "gemini-2.5-flash",
            },
        }
    },
}


IMPORT_STRINGS: list[str] = ["DOCUMENT_CONVERSION_QUERY_HELPER"]


def perform_import(val, setting_name):
    if val is None:
        return None
    if isinstance(val, str):
        return import_string(val)
    if isinstance(val, tuple | list):
        return [import_string(item) for item in val]
    return val


class PDFConverterSettings:
    """
    A settings object that allows Wagtail PDF Converter settings to be accessed as properities.
    For example:
        from wagtail_pdf_converter.conf import settings
        print(settings.AI_BACKENDS)
    """

    def __init__(self, user_settings=None, defaults=None, import_strings=None):
        if user_settings:
            self._user_settings = user_settings
        self.defaults = defaults or DEFAULTS
        self.import_strings = import_strings or IMPORT_STRINGS
        self._cached_attrs = set()

    @property
    def user_settings(self):
        if not hasattr(self, "_user_settings"):
            self._user_settings = getattr(django_settings, "WAGTAIL_PDF_CONVERTER", {})
        return self._user_settings

    def _deep_merge(self, base, overrides):
        """
        Recursively merge two dictionaries.
        """
        result = base.copy()
        for key, value in overrides.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def __getattr__(self, attr):
        if attr not in self.defaults:
            raise AttributeError(f"Invalid PDF Converter setting: '{attr}'")

        try:
            # Check if user setting is provided
            val = self.user_settings[attr]

            # If both default and user value are dicts, do a deep dict merge
            if isinstance(val, dict) and isinstance(self.defaults[attr], dict):
                val = self._deep_merge(self.defaults[attr], val)
        except KeyError:
            # Fall back to default
            val = self.defaults[attr]

        # Validate CONVERSION_STATUS_DISPLAY
        if attr == "CONVERSION_STATUS_DISPLAY" and val is not None:
            valid = (constants.ConversionStatusDisplay.INDEX_VIEW, constants.ConversionStatusDisplay.EDIT_VIEW)
            if val not in valid:
                raise ImproperlyConfigured(
                    f"Invalid CONVERSION_STATUS_DISPLAY value: {val!r}. "
                    f"Must be one of {valid} or None (show in both views)."
                )

        # Coerce import strings
        if attr in self.import_strings:
            val = perform_import(val, attr)

        # Cache the result
        self._cached_attrs.add(attr)
        setattr(self, attr, val)
        return val

    def reload(self):
        for attr in self._cached_attrs:
            delattr(self, attr)
        self._cached_attrs.clear()
        if hasattr(self, "_user_settings"):
            delattr(self, "_user_settings")


settings = PDFConverterSettings(None, DEFAULTS, IMPORT_STRINGS)


def reload_settings(*args, **kwargs):
    setting = kwargs["setting"]
    if setting == "WAGTAIL_PDF_CONVERTER":
        settings.reload()


setting_changed.connect(reload_settings)

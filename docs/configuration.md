---
icon: lucide/settings
---

# Configuration

All settings go in a single `WAGTAIL_PDF_CONVERTER` dict. You only need the keys you want to change — everything else falls back to its default.

```python
WAGTAIL_PDF_CONVERTER = {
    "AI_BACKENDS": {
        "default": {
            "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
            "CONFIG": {
                "API_KEY": os.environ.get("GEMINI_API_KEY", ""),
            },
        }
    },
    "AUTO_CONVERT_PDFS": True,
}
```

## Settings reference

| Setting                            | Default                                                       | Description                                                                                                                                                                                                                               |
| ---------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AI_BACKENDS`                      | _(dict)_                                                      | Required. Configuration for AI models. See [AI Backends](#ai-backends).                                                                                                                                                                   |
| `AUTO_CONVERT_PDFS`                | `False`                                                       | When `True`, triggers conversion automatically on each document save (after the initial upload).                                                                                                                                          |
| `PDF_CONVERSION_TIMEOUT_HOURS`     | `3`                                                           | How long a conversion can stay in `PROCESSING` before `cleanup_stuck_conversions` marks it `FAILED`.                                                                                                                                      |
| `CHUNK_PAGE_THRESHOLD`             | `50`                                                          | PDFs with more pages than this are split into chunks before conversion.                                                                                                                                                                   |
| `EXTRACTED_IMAGES_COLLECTION_NAME` | `"Converted PDFs Images"`                                     | The Wagtail collection where images extracted from PDFs are stored.                                                                                                                                                                       |
| `CONVERSATIONAL_PHRASES`           | _(list)_                                                      | Phrases that indicate an AI conversational response leaked into the output. Lines matching these are stripped from the Markdown.                                                                                                          |
| `ENABLE_ADMIN_EXTENSIONS`          | `False`                                                       | Enables the enhanced Document listing view in Wagtail admin. See [Admin UI](guides/admin-ui.md).                                                                                                                                          |
| `CONVERSION_STATUS_DISPLAY`        | `None`                                                        | Where to show conversion status in the admin: `"index_view"` (listing column only), `"edit_view"` (edit form only), or `None` (both). See [Admin UI](guides/admin-ui.md).                                                                 |
| `FILTER_PDF_IMAGES`                | `True`                                                        | When `True`, hides images stored in `EXTRACTED_IMAGES_COLLECTION_NAME` from the image admin listing and image chooser. Users can still access them by selecting that collection explicitly. Set to `False` to show all images everywhere. |
| `BASE_TEMPLATE`                    | `"wagtail_pdf_converter/base.html"`                           | The base template extended by the HTML document view.                                                                                                                                                                                     |
| `DOCUMENT_CONVERSION_QUERY_HELPER` | `"wagtail_pdf_converter.utils.DocumentConversionQueryHelper"` | A class used to filter which documents are eligible for conversion. Override this to apply custom logic (e.g., taxonomies).                                                                                                               |
| `PROMPTS`                          | _(dict)_                                                      | AI prompt templates. Override individual keys to customise conversion behaviour.                                                                                                                                                          |

## AI Backends

The package is model-agnostic and uses a backend-based architecture. You must configure at least a `default` backend in `AI_BACKENDS`.

### Gemini Backend

The default backend uses Google's Gemini models via the `google-genai` SDK.

```python
WAGTAIL_PDF_CONVERTER = {
    "AI_BACKENDS": {
        "default": {
            "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
            "CONFIG": {
                "API_KEY": os.environ.get("GEMINI_API_KEY", ""),
                "IMAGE_MODEL": "gemini-2.5-flash",
                "CONVERSION_MODEL": "gemini-2.5-flash",
            },
        }
    },
}
```

**Config keys:**

- `API_KEY`: Required. Your Google Gemini API key.
- `IMAGE_MODEL`: Optional. The model used to describe extracted images (default: `gemini-2.5-flash`).
- `CONVERSION_MODEL`: Optional. The model used for PDF-to-Markdown conversion (default: `gemini-2.5-flash`).

### Custom Backends

You can implement your own backend by subclassing `wagtail_pdf_converter.services.backends.base.AIPDFBackend` and pointing to it in your settings.

## Advanced Filtering

By default, the package attempts to convert any PDF that isn't marked as "exempt". If you need to restrict conversion to a specific subset of documents (e.g., based on a custom taxonomy, tags, or a "Convert to Markdown" checkbox), you can provide a custom **Query Helper**.

This custom helper will govern both individual auto-conversions (via the `post_save` signal) and batch conversions (via the `convert_documents` management command).

### Customizing eligibility

1.  **Create a custom helper class** that inherits from `DocumentConversionQueryHelper`.
2.  **Override `eligible_for_conversion`** (and optionally `failed_conversions`) to return your filtered QuerySet.
3.  **Point the setting** to your custom class.

```python
# my_app/utils.py
from wagtail_pdf_converter.utils import DocumentConversionQueryHelper

class MyCustomQueryHelper(DocumentConversionQueryHelper):
    @classmethod
    def eligible_for_conversion(cls):
        # 1. Start with the default base filtering (is_pdf, not exempt, etc.)
        qs = super().eligible_for_conversion()

        # 2. Add your custom project-specific filtering
        # Example: only convert documents tagged with "auto-convert"
        return qs.filter(tags__name="auto-convert")

# settings.py
WAGTAIL_PDF_CONVERTER = {
    "DOCUMENT_CONVERSION_QUERY_HELPER": "my_app.utils.MyCustomQueryHelper",
}
```

## Deep merge for dict settings

For `AI_BACKENDS` and `PROMPTS`, your overrides are deep-merged with the defaults rather than replacing them entirely. You can change a single key without copying all the others:

```python
WAGTAIL_PDF_CONVERTER = {
    "PROMPTS": {
        # Only this key is overridden; all other prompts keep their defaults
        "PDF_CONVERSION_TEMPLATE": "Convert this PDF to Markdown. Extra rules: ...",
    },
}
```

## Prompts reference

The `PROMPTS` dict accepts these keys:

| Key                                | Purpose                                                      |
| ---------------------------------- | ------------------------------------------------------------ |
| `PDF_CONVERSION_TEMPLATE`          | Main prompt for converting a PDF page to Markdown            |
| `MARKDOWN_CONTINUATION`            | Prompt used when continuing Markdown across chunk boundaries |
| `IMAGE_DESCRIPTION_TEMPLATE`       | Prompt template for describing an extracted image            |
| `IMAGE_SINGLE_DESCRIPTION`         | Prompt for describing a single image in isolation            |
| `IMAGE_BATCH_DESCRIPTION`          | Prompt for describing a batch of images                      |
| `SINGLE_IMAGE_OUTPUT_INSTRUCTIONS` | Output format instructions for single-image descriptions     |
| `BATCH_IMAGE_OUTPUT_INSTRUCTIONS`  | Output format instructions for batched image descriptions    |

## Configuring wagtail-markdown

The `pdf_markdown` template filter renders Markdown through `wagtail-markdown`. Without a `WAGTAILMARKDOWN` settings block, rendering falls back to minimal defaults — no table support, no footnotes, no heading anchors, and HTML tags emitted by the converter (such as `<figure>`, `<sup>`, and `<aside>`) are stripped by the sanitiser.

Add this to your Django settings and extend it to suit your project:

```python
WAGTAILMARKDOWN = {
    "extensions": [
        "tables",
        "fenced_code",
        "def_list",
        "footnotes",
        "toc",
        "attr_list",
        "md_in_html",
        "codehilite",
        "sane_lists",
        "wagtail_pdf_converter.markdown_extensions",
    ],
    "allowed_settings_mode": "extend",   # merge with wagtail-markdown's defaults
    "extensions_settings_mode": "extend",
    "allowed_tags": ["figure", "figcaption", "sup", "sub", "aside"],
    "allowed_attributes": {},
}
```

The `"extend"` modes merge your values with `wagtail-markdown`'s built-in defaults rather than replacing them, so you don't need to copy the full allow-list. Add any additional HTML tags the converter emits that you want to preserve to `allowed_tags`.

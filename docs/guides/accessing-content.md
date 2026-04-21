---
icon: lucide/code
---

# Accessing converted content

When conversion completes, the Markdown output is stored in a `DocumentConversion` row linked to the document. This row is only loaded when you explicitly access it, keeping the Document table lightweight.

## In templates

Access converted content via the `pdf_conversion` reverse relation:

```html+django
{% load pdf_markdown_tags %}
{% if document.pdf_conversion.converted_content %}
    {{ document.pdf_conversion.converted_content|pdf_markdown }}
{% endif %}
```

The `pdf_markdown` template filter renders Markdown as safe HTML using the package's configured Markdown extensions.

## In Python

```python
# Check if conversion is complete — reads conversion_status only, no extra query
document.has_converted_content()  # True / False

# Get the HTML view URL — returns None if not yet converted
document.get_html_url()

# Read the Markdown content — triggers a query to the DocumentConversion table
try:
    content = document.pdf_conversion.converted_content
except document.__class__.pdf_conversion.RelatedObjectDoesNotExist:
    content = None
```

`has_converted_content()` reads `conversion_status` on the Document row directly, so it's safe to call in a tight loop without loading Markdown into memory.

## Search indexing

`PDFConversionMixin` registers `get_converted_content_for_search()` as a Wagtail search field. The database search backend picks this up automatically. Documents without a conversion row are indexed with an empty value — no configuration needed.

!!! note "Elasticsearch / OpenSearch"
    Additional denormalisation configuration may be required for non-database search backends.

## Controlling search engine indexing

`DocumentConversion.allow_indexing` controls whether the HTML view gets a `noindex` meta tag. It defaults to `False` — all HTML views are excluded from search engine results unless you opt in:

```python
document.pdf_conversion.allow_indexing = True
document.pdf_conversion.save(update_fields=["allow_indexing"])
```

## Conversion statuses

The `conversion_status` field on the Document can hold these values:

| Status           | Meaning                                                   |
| ---------------- | --------------------------------------------------------- |
| `pending`        | PDF detected, waiting to be converted                     |
| `processing`     | Conversion task is running                                |
| `completed`      | Conversion succeeded; `pdf_conversion` row exists         |
| `failed`         | Conversion failed; see `conversion_metrics` for the error |
| `exempt`         | Excluded from conversion via `conversion_exempt=True`     |
| `not_applicable` | File is not a PDF                                         |

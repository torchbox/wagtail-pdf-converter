---
icon: lucide/layout-template
---

# Customising templates

The HTML view for converted documents is rendered by `wagtail_pdf_converter/document.html`. Override it in your project's templates directory to change the output.

## Changing the base template

By default, the document template extends a minimal HTML5 skeleton (`wagtail_pdf_converter/base.html`). To wrap converted documents in your project's main layout instead, update the `BASE_TEMPLATE` setting:

```python
WAGTAIL_PDF_CONVERTER = {
    "BASE_TEMPLATE": "base.html",  # your project's base template
}
```

## Available blocks

Override any of these blocks in your custom `document.html`:

| Block               | Description                                                       |
| ------------------- | ----------------------------------------------------------------- |
| `meta_tags`         | Extra `<meta>` tags in the `<head>`                               |
| `page_title`        | Contents of the `<title>` tag                                     |
| `disclaimer`        | AI-generated content warning (`<aside>`)                          |
| `content_header`    | Header section containing title and metadata                      |
| `file_info`         | Publication date and file format info (child of `content_header`) |
| `download_original` | "Download original PDF" link (child of `content_header`)          |
| `pdf_content`       | The main content area where converted Markdown renders            |

## Example

Add a custom header above the default content:

```html+django
{% extends "wagtail_pdf_converter/document.html" %}

{% block content_header %}
    <div class="my-custom-header">
        <h1>{{ document.title }}</h1>
        <p>Converted by My App</p>
    </div>
{% endblock %}
```

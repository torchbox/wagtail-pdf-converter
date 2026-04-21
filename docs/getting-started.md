---
icon: lucide/rocket
---

# Getting started

Install the package, wire it up, and get your first PDF converting in about 10 minutes.

## 1. Install the package

```bash
python -m pip install wagtail-pdf-converter
```

## 2. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    "wagtail_pdf_converter",  # Must come before wagtail.images and wagtail.documents
    # ...
    "wagtail.images",
    "wagtail.documents",
    # ...
    "django_tasks",
    "django_tasks.backends.database",  # Registers the DBTaskResult model
    "wagtailmarkdown",
]
```

Place `wagtail_pdf_converter` before `wagtail.images` and `wagtail.documents` so its admin view overrides take effect.

## 3. Wire up the URLs

Add the package URLs to your project's `urls.py`. These serve the public HTML view for converted documents:

```python
from django.urls import include, path
from wagtail.documents import urls as wagtaildocs_urls

urlpatterns = [
    # ...
    path("documents/", include(wagtaildocs_urls)),           # existing — keep this
    path("documents/", include("wagtail_pdf_converter.urls")),  # add this alongside
]
```

The package URLs add only the `/documents/<id>/html/` route. They do **not** include Wagtail's standard document-serving patterns, so keep the existing `wagtaildocs_urls` entry — removing it would break document downloads.

## 4. Extend your Document model

Apply `PDFConversionMixin` to your custom Document model. The mixin must come before `AbstractDocument` in the MRO:

```python
from wagtail.documents.models import AbstractDocument
from wagtail_pdf_converter.models import PDFConversionMixin

class CustomDocument(PDFConversionMixin, AbstractDocument):
    admin_form_fields = PDFConversionMixin.admin_form_fields
```

`PDFConversionMixin.admin_form_fields` already includes all standard Wagtail document fields — it is equivalent to `AbstractDocument.admin_form_fields + ("conversion_exempt",)`. You don't need to merge them manually.

If you don't have a custom Document model yet, create one first. Wagtail requires a custom model to use this mixin — you can't apply it to the built-in `Document` class directly.

Point Wagtail at your model and enable the admin form integration by adding these settings:

```python
WAGTAILDOCS_DOCUMENT_MODEL = "myapp.CustomDocument"

WAGTAILDOCS_DOCUMENT_FORM_BASE = "wagtail_pdf_converter.forms.PDFConverterDocumentForm"
```

`WAGTAILDOCS_DOCUMENT_FORM_BASE` is required for the admin integration — without it, editors won't see the conversion status, the retry button, or the "Edit accessible version" link.

## 5. Run migrations

```bash
python manage.py migrate
```

This creates the `DocumentConversion` table that stores the Markdown output separately from the Document table.

!!! note "Installing into an existing project?"
    The migration adds `is_pdf` and `conversion_status` fields with defaults, but doesn't inspect your existing files. Run this command to fix up those flags for all pre-existing documents:
    ```bash
    python manage.py update_document_conversion_status
    ```
    Once that's done, use `convert_documents --all` when you're ready to queue them for conversion.

## 6. Configure the package

Add a `WAGTAIL_PDF_CONVERTER` dict to your Django settings:

```python
WAGTAIL_PDF_CONVERTER = {
    "AI_BACKENDS": {
        "default": {
            "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
            "CONFIG": {
                "API_KEY": "your-api-key-here",
            },
        }
    },
    "AUTO_CONVERT_PDFS": True,  # Trigger conversion automatically on save
}
```

!!! warning "API key security"
    Never commit your API key to version control. Use an environment variable:
    ```python
    import os
    WAGTAIL_PDF_CONVERTER = {
        "AI_BACKENDS": {
            "default": {
                "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                "CONFIG": {
                    "API_KEY": os.environ.get("GEMINI_API_KEY", ""),
                },
            }
        },
    }
    ```

!!! note "Manual conversion"
    If you leave `AUTO_CONVERT_PDFS` at its default (`False`), conversions won't trigger automatically. Use the `convert_documents` management command instead — see [Management commands](guides/management-commands.md).

## 7. Set up the django-tasks worker

`wagtail-pdf-converter` uses [django-tasks](https://github.com/realOrangeOne/django-tasks) for background processing. Add the task backend to your settings:

```python
TASKS = {
    "default": {
        # Required: defining TASKS disables django-tasks' automatic default backend.
        # Any package that uses @task() without an explicit backend= argument
        # (e.g. wagtail.search) will fail with InvalidTaskBackendError without this.
        "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
    },
    "pdf_conversion": {
        "BACKEND": "django_tasks.backends.database.DatabaseBackend",
    },
}
```

Then run the worker:

```bash
python manage.py db_worker --queue-name pdf_conversion
```

In production, run the worker as a persistent process — systemd, a Procfile, or your platform's equivalent.

## 8. Verify

1. Log in to the Wagtail admin and upload a PDF.
2. Open the document and save it again — this triggers the conversion signal.
3. Watch the status move from **Pending** → **Processing** → **Completed**.
4. Visit `/documents/<id>/html/` to see the HTML version, or call `document.get_html_url()` in code.

!!! note "Conversion time"
    Large PDFs with many pages or images can take several minutes. PDFs over 50 pages are split into chunks and processed in parallel.

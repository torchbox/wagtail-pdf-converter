---
icon: lucide/terminal
---

# Management commands

## Seeing conversion progress

Progress messages (e.g. "Converting chunk 1 of 4") are emitted via Python's logging system. Without a logger configured for `wagtail_pdf_converter`, they are silently swallowed and the command appears to hang with no output.

Add this to your `LOGGING` config to see them in the console:

```python
LOGGING = {
    "version": 1,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "wagtail_pdf_converter": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
```

---

## convert_documents

Trigger PDF-to-Markdown conversions from the command line.

### Convert a single document

```bash
python manage.py convert_documents --document-id 42
```

This enqueues a background task. Use `--wait` to block until it finishes instead:

```bash
python manage.py convert_documents --document-id 42 --wait
```

Or `--follow` to enqueue and then watch the status update live:

```bash
python manage.py convert_documents --document-id 42 --follow
```

### Convert all eligible documents

Eligible documents are PDFs that are not exempt and have a `pending` or `failed` status:

```bash
python manage.py convert_documents --all
```

### Retry failed conversions only

```bash
python manage.py convert_documents --failed-only
```

### Check a document's status

```bash
python manage.py convert_documents --document-id 42 --status
```

### Preview without converting

Add `--dry-run` to any of the above to see what would be affected without making changes:

```bash
python manage.py convert_documents --all --dry-run
```

---

## cleanup_stuck_conversions

Finds documents stuck in `PROCESSING` longer than the configured timeout and marks them `FAILED`. Use it when a worker crashes or gets restarted mid-conversion.

```bash
python manage.py cleanup_stuck_conversions
```

The default timeout comes from `PDF_CONVERSION_TIMEOUT_HOURS` (3 hours). Override it for a one-off run:

```bash
python manage.py cleanup_stuck_conversions --timeout-hours 1
```

Preview which documents would be affected without changing anything:

```bash
python manage.py cleanup_stuck_conversions --dry-run
```

!!! note "Schedule this command"
    Run `cleanup_stuck_conversions` on a schedule — cron, Celery Beat, or your platform's equivalent. Once per hour is a reasonable interval.

---

## update_document_conversion_status

Re-evaluates `is_pdf` (by reading file content) and re-derives `conversion_status` for every document in the database, in batches of 1000.

```bash
python manage.py update_document_conversion_status
```

Run this after a bulk import via data migration or `bulk_create` — anything that bypasses `PDFConversionMixin.save()`. Without the mixin's save logic, `is_pdf` won't be set and no conversions will trigger. This command corrects the flags and marks new PDFs as `pending`, ready for `convert_documents --all`.

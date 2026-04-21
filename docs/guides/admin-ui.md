---
icon: lucide/layout-dashboard
---

# Admin UI

## Always available

These features are registered automatically — no configuration needed.

### Conversion Metrics dashboard

A **Conversion Metrics** item appears in the Wagtail admin sidebar. It shows a breakdown of conversion statuses across your document library: how many are pending, processing, completed, or failed.

### Retry Conversion

On any document's edit page, a **Retry Conversion** action re-queues a failed conversion or forces a re-run after updating the document.

### Edit Accessible Version

Once a conversion completes, an **Edit Accessible Version** button appears on the document edit page. It opens a dedicated Markdown editor, so you can fix up AI output without re-running the full conversion.

This view loads separately from the main document edit page, so the large Markdown payload isn't loaded into memory on every document edit.

### Conversion status on the edit page

For PDF documents, a read-only **Conversion status** field is shown on the document edit page above the action buttons. This is controlled by `CONVERSION_STATUS_DISPLAY` — see [Controlling where status is shown](#controlling-where-status-is-shown) below.

---

## Requires ENABLE_ADMIN_EXTENSIONS

The features below override Wagtail's default Document listing view. They're off by default to avoid unexpected changes in your admin.

```python
WAGTAIL_PDF_CONVERTER = {
    "ENABLE_ADMIN_EXTENSIONS": True,
}
```

This also loads the admin CSS for the enhanced listing.

### Enhanced Document listing

When enabled, the Document index view gets:

- An **HTML version** status column showing each document's conversion status
- A **conversion status filter** in the sidebar
- Quick action links to retry conversion or view the HTML version inline

The status column can be hidden via `CONVERSION_STATUS_DISPLAY` — see [Controlling where status is shown](#controlling-where-status-is-shown) below.

### Controlling where status is shown

By default (`CONVERSION_STATUS_DISPLAY = None`), conversion status appears in both the document listing column and the document edit page. Set it to show in only one place:

```python
WAGTAIL_PDF_CONVERTER = {
    "ENABLE_ADMIN_EXTENSIONS": True,
    "CONVERSION_STATUS_DISPLAY": "index_view",  # listing column only
    # or: "edit_view"  — edit page only
}
```

### Using with a custom index view

If you already have a custom `IndexView` subclass, apply `PDFConverterIndexViewMixin` rather than pointing at `CustomDocumentIndexView` directly:

```python
from wagtail.documents.views.documents import IndexView
from wagtail_pdf_converter.admin_views import PDFConverterIndexViewMixin

class MyDocumentIndexView(PDFConverterIndexViewMixin, IndexView):
    # your existing customisations
    pass
```

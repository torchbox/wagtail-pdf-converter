EXTRACTED_IMAGES_COLLECTION_NAME: str = "Converted PDFs Images"
# The page count above which PDFs are automatically split into smaller chunks
# for conversion. This value was determined through trial and error to balance
# API performance and avoid context length or timeout issues with large documents.
PDF_CONVERTER_CHUNK_PAGE_THRESHOLD_DEFAULT: int = 50


class ConversionStatusDisplay:
    """
    Valid values for the CONVERSION_STATUS_DISPLAY package setting.

    ``INDEX_VIEW``  – show status column in the document index view only.
    ``EDIT_VIEW``   – show status field in the document edit view only.
    ``None`` (default) – show status in both views.
    """

    INDEX_VIEW = "index_view"
    EDIT_VIEW = "edit_view"

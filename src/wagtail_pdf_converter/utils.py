import hashlib
import logging
import textwrap

from io import BytesIO

import puremagic

from django.core.files.images import ImageFile
from django.db import IntegrityError
from wagtail.documents import get_document_model
from wagtail.images import get_image_model
from wagtail.images.models import AbstractImage
from wagtail.models import Collection

from .conf import settings as conf_settings
from .constants import EXTRACTED_IMAGES_COLLECTION_NAME
from .enums import ConversionStatus


logger = logging.getLogger(__name__)

Image: type[AbstractImage] = get_image_model()
Document = get_document_model()


class DocumentConversionQueryHelper:
    """Helper class for common document queries used in PDF conversion."""

    @classmethod
    def eligible_for_conversion(cls):
        """
        Returns a queryset for documents that are eligible for conversion.

        Eligible documents are PDFs that are not exempt and have a 'pending'
        or 'failed' conversion status.
        """
        return Document.objects.filter(
            is_pdf=True,
            conversion_exempt=False,
            conversion_status__in=[
                ConversionStatus.PENDING,
                ConversionStatus.FAILED,
            ],
        )

    @classmethod
    def failed_conversions(cls):
        """Returns queryset for failed conversions that can be retried."""
        return Document.objects.filter(
            is_pdf=True,
            conversion_exempt=False,
            conversion_status=ConversionStatus.FAILED,
        )


def get_mime_type_from_bytes(data: bytes) -> str:
    """
    Determine MIME type from byte data using puremagic.

    Args:
        data: The raw bytes to identify.

    Returns:
        The MIME type string, or "application/octet-stream" if unidentifiable.
    """
    try:
        return puremagic.from_string(data, mime=True)
    except puremagic.PureError:
        # Fallback to a generic binary type if puremagic can't determine the type
        return "application/octet-stream"


def add_image_to_wagtail_collection(
    image_data: bytes,
    image_name: str,
    collection_name: str = EXTRACTED_IMAGES_COLLECTION_NAME,
    title: str | None = None,
    description: str | None = None,
) -> str:
    """
    Adds an image to a Wagtail collection and returns its full, absolute URL.
    This function is idempotent and will not create duplicates of the same image.

    Args:
        image_data: The raw image data in bytes.
        image_name: The original, descriptive file name for the image.
        collection_name: The name of the collection to add the image to.
        title: Optional custom title for the image (defaults to image_name).
        description: Optional description for the image.

    Returns:
        The absolute URL of the uploaded image's rendition.
    """
    # 1. Calculate the SHA-1 hash of the image content, which matches
    # wagtail.images.models.AbstractImage.file_hash.
    image_hash = hashlib.sha1(image_data, usedforsecurity=False).hexdigest()

    # Get or create the collection.
    root_collection = Collection.get_first_root_node()
    try:
        collection = root_collection.get_children().get(name=collection_name)
    except Collection.DoesNotExist:
        try:
            collection = root_collection.add_child(name=collection_name)
            logger.info(f"Created new Wagtail Collection: '{collection_name}'")
        except IntegrityError:
            # Another thread created the collection concurrently — fetch it.
            collection = root_collection.get_children().get(name=collection_name)
    except Collection.MultipleObjectsReturned:
        collection = root_collection.get_children().filter(name=collection_name).first()
    except Exception as e:
        logger.error(f"Error finding collection '{collection_name}': {e}")
        collection = root_collection  # Fallback to root collection

    # 2. Check for an existing image using the content hash.
    image = Image.objects.filter(file_hash=image_hash, collection=collection).first()

    if image:
        logger.info(f"Image '{image_name}' (hash: {image_hash}) already exists. Using existing.")
    else:
        # 3. If no duplicate is found, create the new image.
        image_title = title if title is not None else image_name

        # Truncate description to fit database constraint (255 chars max)
        if description is not None:
            image_description = textwrap.shorten(description, width=250, placeholder="...")
            if len(description) > 250:
                logger.warning(
                    f"Truncated description for image '{image_name}' from "
                    f"{len(description)} to {len(image_description)} chars"
                )
        else:
            image_description = ""

        logger.info(f"Creating new image '{image_title}'")
        # Use the original image_name, let Wagtail handle slugification.
        image_file = ImageFile(BytesIO(image_data), name=image_name)
        image = Image(
            title=image_title,
            description=image_description,
            file=image_file,
            collection=collection,
        )

        # Manually trigger hash calculation to ensure the `file_hash` is populated
        # before saving. Wagtail's automatic `pre_save` signal for this can be
        # unreliable in some environments (e.g., tests), which would break the
        # content-based idempotency check.
        image._set_file_hash()

        image.save()
        logger.info(f"Saved new image: {image.title} -> {image.file.name}")

    # 4. Get rendition and construct absolute URL.
    rendition = image.get_rendition("original")
    return rendition.full_url


def exclude_pdf_images(queryset, request):
    """
    Exclude images in the PDF-extracted images collection from *queryset*,
    unless the request includes an explicit ``collection_id`` filter.

    When ``collection_id`` is present the queryset is returned unmodified so
    that the user's explicit collection selection is respected:

    - Selecting the PDF collection → PDF images shown.
    - Selecting another collection → images already scoped, filter is redundant.
    - No collection selected → PDF images hidden.
    """
    if request.GET.get("collection_id"):
        return queryset
    return queryset.exclude(collection__name=conf_settings.EXTRACTED_IMAGES_COLLECTION_NAME)

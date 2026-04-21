import os

from io import BytesIO
from unittest.mock import MagicMock

import factory
import pytest

from django.conf import settings
from django.core.files.images import ImageFile
from django.test import TestCase
from PIL import Image as PILImage
from wagtail.images import get_image_model
from wagtail.models import Collection
from wagtail_factories import ImageFactory

from wagtail_pdf_converter.constants import EXTRACTED_IMAGES_COLLECTION_NAME
from wagtail_pdf_converter.utils import (
    add_image_to_wagtail_collection,
    exclude_pdf_images,
    get_mime_type_from_bytes,
)


Image = get_image_model()


class TestGetMimeTypeFromBytes(TestCase):
    def test_identifies_png_correctly(self):
        """Test that PNG images are correctly identified."""
        test_image_bytes = factory.django.ImageField()._make_data({"width": 100, "height": 100, "format": "PNG"})
        mime_type = get_mime_type_from_bytes(test_image_bytes)
        self.assertEqual(mime_type, "image/png")

    def test_identifies_jpeg_correctly(self):
        """Test that JPEG images are correctly identified."""
        test_image_bytes = factory.django.ImageField()._make_data({"width": 100, "height": 100, "format": "JPEG"})
        mime_type = get_mime_type_from_bytes(test_image_bytes)
        self.assertIn(mime_type, ["image/jpeg", "image/jpg"])

    def test_returns_fallback_for_unidentifiable_data(self):
        """Test that unidentifiable data returns fallback MIME type."""
        random_bytes = b"not a valid file format"
        mime_type = get_mime_type_from_bytes(random_bytes)
        self.assertEqual(mime_type, "application/octet-stream")


class TestAddImageToWagtailCollection(TestCase):
    @classmethod
    def setUpTestData(cls):
        dummy_image = ImageFactory.build()
        cls.image_data = dummy_image.file.read()
        cls.collection_name = "Test PDF Converter Collection"
        cls.title = "Test Title"
        cls.description = "A meaningful description for the test image."

    def test_creates_image_and_new_collection_successfully(self):
        """
        Test that a new image is created correctly and that a new
        collection is created when it doesn't already exist.
        """
        image_url = add_image_to_wagtail_collection(
            image_data=self.image_data,
            image_name="image1.jpg",
            collection_name=self.collection_name,
            title=self.title,
            description=self.description,
        )

        # Check that the collection was created
        self.assertTrue(Collection.objects.filter(name=self.collection_name).exists())
        collection = Collection.objects.get(name=self.collection_name)

        # Check that the image was created and has the correct attributes
        self.assertTrue(Image.objects.filter(title=self.title).exists())
        image = Image.objects.get(title=self.title)
        self.assertEqual(image.collection, collection)
        self.assertEqual(image.description, self.description)

        # Check the returned URL
        base_filename = os.path.basename(image.file.name)
        filename_without_ext, _ = os.path.splitext(base_filename)
        self.assertIn(".original.jpg", image_url)
        self.assertIn(settings.MEDIA_URL, image_url)
        self.assertIn(filename_without_ext, image_url)

    def test_uses_existing_collection_if_name_matches(self):
        """
        Test that if a collection with the given name already exists,
        the function uses it instead of creating a new one.
        """
        # Create the collection first
        root_collection = Collection.get_first_root_node()
        root_collection.add_child(name=self.collection_name)
        self.assertEqual(Collection.objects.filter(name=self.collection_name).count(), 1)

        add_image_to_wagtail_collection(
            image_data=self.image_data,
            image_name="image2.jpg",
            collection_name=self.collection_name,
            title=self.title,
            description=self.description,
        )

        # Assert that a new collection was NOT created
        self.assertEqual(Collection.objects.filter(name=self.collection_name).count(), 1)

        # Check that the new image is in the pre-existing collection
        image = Image.objects.get(title=self.title)
        collection = Collection.objects.get(name=self.collection_name)
        self.assertEqual(image.collection, collection)

    def test_idempotency_with_identical_image_data(self):
        """
        Test that calling the function twice with the exact same image data
        results in only one image being created.
        """
        add_image_to_wagtail_collection(
            image_data=self.image_data,
            image_name="unique_image.jpg",
            collection_name=self.collection_name,
            title="First Upload Title",
        )

        # Check that one image was created
        self.assertEqual(Image.objects.count(), 1)
        first_image = Image.objects.first()

        # Call the function a second time with the same data but a different title
        add_image_to_wagtail_collection(
            image_data=self.image_data,
            image_name="unique_image.jpg",
            collection_name=self.collection_name,
            title="Second Upload Title",
        )

        # Assert that a new image was NOT created
        self.assertEqual(Image.objects.count(), 1)
        second_image_lookup = Image.objects.first()

        # Assert that the image found is the same as the first one
        self.assertEqual(first_image.pk, second_image_lookup.pk)
        # The title should remain from the first upload
        self.assertEqual(second_image_lookup.title, "First Upload Title")

    def test_image_title_defaults_to_image_name_when_not_provided(self):
        """
        Test that the image's title defaults to its filename if a
        title is not explicitly provided.
        """
        image_name = "default_title_test.png"
        add_image_to_wagtail_collection(
            image_data=self.image_data,
            image_name=image_name,
            collection_name=self.collection_name,
            title=None,
        )

        self.assertTrue(Image.objects.filter(title=image_name).exists())

    def test_long_description_is_truncated(self):
        """
        Test that a description longer than 250 characters is correctly
        shortened and ends with an ellipsis.
        """
        long_description = "a" * 300
        self.assertTrue(len(long_description) > 250)

        add_image_to_wagtail_collection(
            image_data=self.image_data,
            image_name="truncation_test.jpg",
            collection_name=self.collection_name,
            title="Truncation Test",
            description=long_description,
        )

        image = Image.objects.get(title="Truncation Test")
        self.assertTrue(len(image.description) <= 255)
        self.assertTrue(image.description.endswith("..."))

    def test_handles_multiple_collections_with_same_name(self):
        """
        Test that the function does not crash and correctly selects a
        collection when multiple collections with the same name exist.
        """
        root_collection = Collection.get_first_root_node()
        collection1 = root_collection.add_child(name=self.collection_name)
        collection2 = root_collection.add_child(name=f"{self.collection_name}_temp")
        # Manually rename the second collection to match the first
        collection2.name = self.collection_name
        collection2.save()

        self.assertEqual(Collection.objects.filter(name=self.collection_name).count(), 2)

        # The function should run without raising a MultipleObjectsReturned error
        try:
            add_image_to_wagtail_collection(
                image_data=self.image_data,
                image_name="a-test-image.jpg",
                collection_name=self.collection_name,
                title=self.title,
            )
        except Collection.MultipleObjectsReturned:
            self.fail("Function raised MultipleObjectsReturned unexpectedly.")

        # Assert that no new collection was created
        self.assertEqual(Collection.objects.filter(name=self.collection_name).count(), 2)

        # Check that the image was added to one of the existing collections
        image = Image.objects.get(title=self.title)
        self.assertIn(image.collection, [collection1, collection2])


def _make_request(collection_id=None):
    """Return a minimal mock request with optional collection_id in GET."""
    req = MagicMock()
    req.GET = {"collection_id": str(collection_id)} if collection_id is not None else {}
    return req


def _make_image_file():
    """Return a minimal in-memory PNG ImageFile suitable for Wagtail Image creation."""
    buf = BytesIO()
    PILImage.new("RGB", (10, 10), color="red").save(buf, format="PNG")
    buf.seek(0)
    return ImageFile(buf, name="test.png")


def _create_image(title, collection):
    Image = get_image_model()
    img = Image(title=title, file=_make_image_file(), collection=collection)
    img._set_file_hash()
    img.save()
    return img


@pytest.mark.django_db
class TestExcludePdfImages:
    def _setup(self):
        root = Collection.get_first_root_node()
        pdf_col = root.add_child(name=EXTRACTED_IMAGES_COLLECTION_NAME)
        other_col = root.add_child(name="Editorial Images")
        pdf_img = _create_image("PDF image", pdf_col)
        other_img = _create_image("Editorial image", other_col)
        return pdf_col, other_col, pdf_img, other_img

    def test_excludes_pdf_collection_images_by_default(self):
        """No collection_id in request → PDF images excluded."""
        pdf_col, _, pdf_img, other_img = self._setup()
        Image = get_image_model()
        qs = Image.objects.all()

        result = exclude_pdf_images(qs, _make_request())

        ids = list(result.values_list("id", flat=True))
        assert other_img.id in ids
        assert pdf_img.id not in ids

    def test_passes_through_when_collection_id_present(self):
        """collection_id in request → no filtering, all images returned."""
        pdf_col, _, pdf_img, other_img = self._setup()
        Image = get_image_model()
        qs = Image.objects.all()

        result = exclude_pdf_images(qs, _make_request(collection_id=pdf_col.id))

        ids = list(result.values_list("id", flat=True))
        assert pdf_img.id in ids
        assert other_img.id in ids

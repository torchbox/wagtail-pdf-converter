from io import BytesIO
from unittest import mock

import numpy as np

from django.test import SimpleTestCase
from PIL import Image

from wagtail_pdf_converter.services import image_processing
from wagtail_pdf_converter.services.image_processing import ImageProcessor


def create_test_image(width=100, height=100, color=(255, 255, 255), varied_content=False):
    """
    Create a test image.

    :param width: Image width.
    :param height: Image height.
    :param color: Base color for the image.
    :param varied_content: If True, creates a gradient image.
    :return: Image bytes.
    """
    if varied_content:
        img_array = np.zeros((height, width, 3), dtype=np.uint8)
        for i in range(height):
            for j in range(width):
                img_array[i, j] = [i % 256, j % 256, (i + j) % 256]
        img = Image.fromarray(img_array)
    else:
        img = Image.new("RGB", (width, height), color)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestImageFiltering(SimpleTestCase):
    """Test image filtering logic to determine which images are worth processing."""

    processor = ImageProcessor()
    small_image = create_test_image(width=5, height=5)
    wide_image = create_test_image(width=1000, height=10)
    tall_image = create_test_image(width=10, height=1000)
    uniform_image = create_test_image()
    gradient_image = create_test_image(varied_content=True)
    tiny_image = create_test_image(width=2, height=2)
    small_icon_image = create_test_image(width=150, height=150)

    def test_image_too_small_rejected(self):
        """Test that images smaller than minimum dimensions are rejected."""
        result = self.processor._is_image_useful(self.small_image, 5, 5, "small_test.png")
        self.assertFalse(result)

    def test_image_extreme_aspect_ratio_rejected(self):
        """Test that images with extreme aspect ratios are rejected."""
        result_wide = self.processor._is_image_useful(self.wide_image, 1000, 10, "wide_test.png")
        self.assertFalse(result_wide)

        result_tall = self.processor._is_image_useful(self.tall_image, 10, 1000, "tall_test.png")
        self.assertFalse(result_tall)

    def test_uniform_color_image_rejected(self):
        """Test that images with uniform colors are rejected."""
        result = self.processor._is_image_useful(self.uniform_image, 200, 200, "uniform_test.png")
        self.assertFalse(result)

    def test_gradient_image_accepted(self):
        """Test that images with varied content are accepted."""
        gradient_image = create_test_image(width=200, height=200, varied_content=True)
        result = self.processor._is_image_useful(gradient_image, 200, 200, "gradient_test.png")
        self.assertTrue(result)

    def test_file_size_too_small_rejected(self):
        """Test that images with very small file sizes are rejected."""
        result = self.processor._is_image_useful(self.tiny_image, 2, 2, "tiny_test.png")
        self.assertFalse(result)

    def test_small_icon_image_rejected(self):
        """Test that small icon-like images are rejected."""
        # This image is 150x150, which is less than 160x160, and its size will be small
        image_bytes = self.small_icon_image
        # Ensure the size is under 3kb for the test to be valid. create_test_image produces small pngs.
        self.assertLessEqual(len(image_bytes), 3072)
        result = self.processor._is_image_useful(image_bytes, 150, 150, "small_icon_test.png")
        self.assertFalse(result)

    def test_image_analysis_error_handling(self):
        """Test graceful handling when image analysis fails."""
        invalid_data = b"not an image"
        result = self.processor._is_image_useful(invalid_data, 100, 100, "invalid_test.png")
        self.assertFalse(result)


class TestSpatialImageDetection(SimpleTestCase):
    """Test spatial adjacency detection for image merging."""

    processor = ImageProcessor()

    def _create_mock_rect(self, x0, y0, x1, y1):
        """Create a mock rectangle with specified coordinates."""
        rect = mock.Mock()
        rect.x0, rect.y0, rect.x1, rect.y1 = x0, y0, x1, y1
        return rect

    def test_horizontally_adjacent_rects(self):
        """Test detection of horizontally adjacent rectangles."""
        rect1 = self._create_mock_rect(0, 0, 100, 100)
        rect2 = self._create_mock_rect(100, 0, 200, 100)
        self.assertTrue(self.processor._rects_are_adjacent(rect1, rect2))

    def test_vertically_adjacent_rects(self):
        """Test detection of vertically adjacent rectangles."""
        rect1 = self._create_mock_rect(0, 0, 100, 100)
        rect2 = self._create_mock_rect(0, 100, 100, 200)
        self.assertTrue(self.processor._rects_are_adjacent(rect1, rect2))

    def test_adjacent_with_tolerance(self):
        """Test adjacency detection with small gaps within tolerance."""
        rect1 = self._create_mock_rect(0, 0, 100, 100)
        rect2 = self._create_mock_rect(103, 0, 200, 100)
        self.assertTrue(self.processor._rects_are_adjacent(rect1, rect2, tolerance=5))

    def test_not_adjacent_beyond_tolerance(self):
        """Test that rectangles beyond tolerance are not considered adjacent."""
        rect1 = self._create_mock_rect(0, 0, 100, 100)
        rect2 = self._create_mock_rect(110, 0, 200, 100)
        self.assertFalse(self.processor._rects_are_adjacent(rect1, rect2, tolerance=5))

    def test_completely_separate_rects(self):
        """Test that completely separate rectangles are not adjacent."""
        rect1 = self._create_mock_rect(0, 0, 50, 50)
        rect2 = self._create_mock_rect(100, 100, 150, 150)
        self.assertFalse(self.processor._rects_are_adjacent(rect1, rect2))


class TestSplitImageHandling(SimpleTestCase):
    """Test mask-based and spatial-based image combination."""

    def setUp(self):
        self.processor = ImageProcessor()

    @mock.patch(image_processing.__name__ + ".fitz")
    def test_detect_and_merge_split_images_with_mask(self, mock_fitz):
        """Test detection and merging of images with transparency masks."""
        mock_doc = mock.Mock()
        mock_page = mock.Mock()
        # Mocking get_images() to return an image (xref=123) with a transparency
        # mask (smask xref=456). The page.get_images() method returns a list of tuples,
        # where each tuple contains multiple image properties. For this test, we only
        # need the first two values: the image xref and the smask xref. The
        # remaining values are placeholders and not used in this test.
        mock_page.get_images.return_value = [(123, 456, 0, 0, 0, 0, 0)]
        mock_doc.extract_image.side_effect = [
            {"image": b"base_image", "width": 100, "height": 100, "ext": "png"},
            {"image": b"mask_image", "width": 100, "height": 100, "ext": "png"},
        ]
        (
            mock_base_pix,
            mock_mask_pix,
            mock_combined_pix,
        ) = (
            mock.Mock(),
            mock.Mock(),
            mock.Mock(),
        )
        mock_combined_pix.tobytes.return_value = b"combined_image_data"
        mock_fitz.Pixmap.side_effect = [mock_base_pix, mock_mask_pix, mock_combined_pix]

        result = self.processor._detect_and_merge_split_images(mock_doc, mock_page)

        self.assertIn(123, result)
        self.assertEqual(result[456], "skip")
        self.assertTrue(result[123]["is_combined"])
        self.assertEqual(result[123]["bytes"], b"combined_image_data")

    @mock.patch(image_processing.__name__ + ".fitz")
    def test_detect_and_merge_split_images_mask_error_fallback(self, mock_fitz):
        """Test fallback when mask combination fails."""
        mock_doc = mock.Mock()
        mock_page = mock.Mock()
        mock_page.get_images.return_value = [(123, 456, 0, 0, 0, 0, 0)]
        mock_doc.extract_image.side_effect = [
            {"image": b"base_image", "width": 100, "height": 100, "ext": "png"},
            Exception("Mask extraction failed"),
            {"image": b"base_image", "width": 100, "height": 100, "ext": "png"},
        ]

        result = self.processor._detect_and_merge_split_images(mock_doc, mock_page)

        self.assertIn(123, result)
        self.assertFalse(result[123]["is_combined"])
        self.assertEqual(result[123]["bytes"], b"base_image")

    @mock.patch(image_processing.__name__ + ".fitz")
    def test_detect_and_merge_three_part_spatial_split(self, mock_fitz):
        """Test merging of an image split into three vertical parts."""
        mock_doc = mock.Mock()
        mock_page = mock.Mock()
        # Simulate a page having three separate images (xrefs 1, 2, 3).
        # For this spatial split test, the smask (the second value in the tuple)
        # is 0, as there are no masks involved. We are only interested in the
        # xref of each image part. The remaining values are placeholders.
        mock_page.get_images.return_value = [
            (1, 0, 0, 0, 0, 0, 0),
            (2, 0, 0, 0, 0, 0, 0),
            (3, 0, 0, 0, 0, 0, 0),
        ]
        # Mock the image data for each part. They have the same width and different heights.
        img_data = {
            1: {"image": b"part1", "width": 100, "height": 50, "ext": "png"},
            2: {"image": b"part2", "width": 100, "height": 50, "ext": "png"},
            3: {"image": b"part3", "width": 100, "height": 50, "ext": "png"},
        }
        mock_doc.extract_image.side_effect = lambda xref: img_data.get(xref)

        # Mock the positions of the images on the page. They are stacked vertically
        # and adjacent to each other.
        rects_data = {
            1: [mock.Mock(x0=0, y0=0, x1=100, y1=50)],
            2: [mock.Mock(x0=0, y0=50, x1=100, y1=100)],
            3: [mock.Mock(x0=0, y0=100, x1=100, y1=150)],
        }
        mock_page.get_image_rects.side_effect = lambda xref: rects_data.get(xref)

        # Mocks for pixmap creation and the final combined pixmap
        mock_pix1, mock_pix2, mock_pix3, mock_combined_pix = (
            mock.Mock(),
            mock.Mock(),
            mock.Mock(),
            mock.Mock(),
        )
        mock_pix1.colorspace, mock_pix1.alpha = "RGB", False
        mock_pix2.colorspace, mock_pix2.alpha = "RGB", False
        mock_pix3.colorspace, mock_pix3.alpha = "RGB", False
        mock_combined_pix.tobytes.return_value = b"merged_image"
        mock_fitz.Pixmap.side_effect = [
            mock_pix1,
            mock_pix2,
            mock_pix3,
            mock_combined_pix,
        ]

        # Use a wrapper on the real merge function to verify it's called
        # with the correct group of image parts ([1, 2, 3]).
        with mock.patch.object(
            self.processor,
            "_merge_spatial_images",
            wraps=self.processor._merge_spatial_images,
        ) as mock_merge:
            result = self.processor._detect_and_merge_split_images(mock_doc, mock_page)
            # Verify that merge was called once with all three parts
            mock_merge.assert_called_once_with(mock_doc, [1, 2, 3], mock_page)

        # Assert that the final result correctly represents the merged image.
        # The primary image (xref=1) should contain the merged data, and the other
        # parts (xrefs 2 and 3) should be marked to be skipped.
        self.assertIn(1, result)
        self.assertEqual(result[2], "skip")
        self.assertEqual(result[3], "skip")
        self.assertTrue(result[1]["is_combined"])
        self.assertEqual(result[1]["bytes"], b"merged_image")
        self.assertEqual(result[1]["parts"], [1, 2, 3])


class TestImageExtraction(SimpleTestCase):
    """Test end-to-end image extraction and processing."""

    def setUp(self):
        self.processor = ImageProcessor()

    @mock.patch(image_processing.__name__ + ".fitz")
    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    def test_extract_images_exceeds_threshold(self, mock_add_image, mock_fitz):
        """Test that processing is skipped when image count exceeds threshold."""
        mock_doc = mock.MagicMock()
        mock_page1, mock_page2 = mock.Mock(), mock.Mock()
        # Mocking pages with a large number of images to trigger the threshold.
        # The content of the list items doesn't matter for this test, only the length.
        mock_page1.get_images.return_value = list(range(600))
        mock_page2.get_images.return_value = list(range(500))
        mock_doc.__iter__.return_value = [mock_page1, mock_page2]
        mock_fitz.open.return_value = mock_doc
        mock_ai_client = mock.Mock()
        self.processor.max_images_per_doc = 1000

        result, count = self.processor.extract_and_upload_images(b"fake_pdf", "test-collection", mock_ai_client)

        self.assertEqual(result, [])
        self.assertEqual(count, 0)
        mock_doc.close.assert_called_once()

    @mock.patch(image_processing.__name__ + ".fitz")
    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    def test_extract_images_normal_processing(self, mock_add_image, mock_fitz):
        """Test normal image extraction and processing flow."""
        test_image_bytes = create_test_image(width=200, height=200, varied_content=True)
        mock_doc = mock.MagicMock()
        mock_page = mock.Mock()
        mock_page.number = 0
        # Mocking get_images() to return a single image (xref=123) without a mask (smask=0).
        # The format is (xref, smask, ...), with other values being placeholders.
        mock_page.get_images.return_value = [(123, 0, 0, 0, 0, 0, 0)]
        mock_doc.__iter__.return_value = [mock_page]
        mock_fitz.open.return_value = mock_doc
        mock_doc.extract_image.return_value = {
            "image": test_image_bytes,
            "width": 200,
            "height": 200,
            "ext": "png",
        }
        mock_ai_client = mock.Mock()

        with (
            mock.patch.object(self.processor, "_detect_and_merge_split_images") as mock_detect,
            mock.patch.object(self.processor, "process_image_batch") as mock_process_batch,
        ):
            mock_detect.return_value = {
                123: {
                    "bytes": test_image_bytes,
                    "format": "png",
                    "width": 200,
                    "height": 200,
                    "is_combined": False,
                }
            }
            mock_process_batch.return_value = [
                {
                    "page": 1,
                    "image_name": "page_1_img_0.png",
                    "description": "A test image",
                    "url": "/media/test.png",
                }
            ]

            report, count = self.processor.extract_and_upload_images(b"fake_pdf", "test-collection", mock_ai_client)

            mock_detect.assert_called_once_with(mock_doc, mock_page)
            mock_process_batch.assert_called_once()
            self.assertEqual(len(report), 1)
            self.assertEqual(count, 1)


class TestImageBatchProcessing(SimpleTestCase):
    """Test batch processing coordination."""

    processor = ImageProcessor()
    test_image_bytes = create_test_image()

    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    def test_process_image_batch_meaningful_images(self, mock_add_image):
        """Test processing batch with meaningful images."""
        mock_add_image.return_value = "/media/test.png"
        image_batch = [
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 0,
            }
        ]
        mock_ai_client = mock.Mock()
        mock_ai_client.describe_images_batch.return_value = ["A meaningful chart"]

        results = self.processor.process_image_batch(image_batch, "test-collection", mock_ai_client)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["description"], "A meaningful chart")
        self.assertEqual(results[0]["url"], "/media/test.png")
        mock_add_image.assert_called_once()

    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    def test_process_image_batch_decorative_images_skipped(self, mock_add_image):
        """Test that decorative images are skipped and not uploaded."""
        image_batch = [
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 0,
            }
        ]
        mock_ai_client = mock.Mock()
        mock_ai_client.describe_images_batch.return_value = ["DECORATIVE"]

        results = self.processor.process_image_batch(image_batch, "test-collection", mock_ai_client)

        self.assertEqual(len(results), 0)
        mock_add_image.assert_not_called()

    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    def test_process_image_batch_mixed_types(self, mock_add_image):
        """Test batch processing with mix of meaningful and decorative images."""
        mock_add_image.return_value = "/media/test.png"
        image_batch = [
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 0,
            },
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 1,
            },
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 2,
                "img_index": 0,
            },
        ]
        mock_ai_client = mock.Mock()
        mock_ai_client.describe_images_batch.return_value = [
            "A useful diagram",
            "DECORATIVE",
            "Important chart",
        ]

        results = self.processor.process_image_batch(image_batch, "test-collection", mock_ai_client)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["description"], "A useful diagram")
        self.assertEqual(results[1]["description"], "Important chart")
        self.assertEqual(mock_add_image.call_count, 2)

    def test_process_image_batch_empty_input(self):
        """Test handling of empty image batch."""
        mock_ai_client = mock.Mock()
        results = self.processor.process_image_batch([], "test-collection", mock_ai_client)
        self.assertEqual(results, [])

    @mock.patch(image_processing.__name__ + ".add_image_to_wagtail_collection")
    def test_process_image_batch_upload_error_handling(self, mock_add_image):
        """Test graceful handling when image upload fails."""
        mock_add_image.side_effect = Exception("Upload failed")
        image_batch = [
            {
                "bytes": self.test_image_bytes,
                "format": "png",
                "page_num": 1,
                "img_index": 0,
            }
        ]
        mock_ai_client = mock.Mock()
        mock_ai_client.describe_images_batch.return_value = ["A test image"]

        results = self.processor.process_image_batch(image_batch, "test-collection", mock_ai_client)

        self.assertEqual(len(results), 0)


class TestImageProcessorConfiguration(SimpleTestCase):
    """Test ImageProcessor configuration and parameters."""

    def test_default_parameters(self):
        """Test that default filtering parameters are reasonable."""
        processor = ImageProcessor()
        self.assertEqual(processor.min_image_width, 10)
        self.assertEqual(processor.min_image_height, 10)
        self.assertEqual(processor.min_image_bytes, 100)
        self.assertEqual(processor.min_aspect_ratio, 0.10)
        self.assertEqual(processor.max_aspect_ratio, 10.0)
        self.assertEqual(processor.max_dominant_color_ratio, 0.95)
        self.assertEqual(processor.min_std_dev, 10)
        self.assertEqual(processor.max_images_per_doc, 1000)
        self.assertEqual(processor.small_image_max_width, 160)
        self.assertEqual(processor.small_image_max_height, 160)
        self.assertEqual(processor.small_image_max_bytes, 3072)

    def test_custom_parameters(self):
        """Test initialization with custom parameters."""
        processor = ImageProcessor(max_workers=10, batch_size=20)
        self.assertEqual(processor.max_workers, 10)
        self.assertEqual(processor.batch_size, 20)

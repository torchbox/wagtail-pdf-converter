import concurrent.futures
import logging

from io import BytesIO
from typing import TYPE_CHECKING, Any

import fitz  # PyMuPDF
import humanize
import numpy as np

from PIL import Image

from ..utils import add_image_to_wagtail_collection


if TYPE_CHECKING:
    from .backends import AIPDFBackend

logger = logging.getLogger(__name__)


class ImageProcessor:
    """
    Handles PDF image extraction, filtering, and processing using PyMuPDF.

    References:
    - PyMuPDF Image Recipes: https://pymupdf.readthedocs.io/en/latest/recipes-images.html
    """

    def __init__(self, max_workers: int = 5, batch_size: int = 10):
        """Initialize the image processor."""
        self.max_workers = max_workers
        self.batch_size = batch_size

        # Image filtering parameters tuned by analyzing various documents
        # to effectively remove noise like logos, icons, and page separators.
        self.min_image_width = 10
        self.min_image_height = 10
        self.min_image_bytes = 100
        self.min_aspect_ratio = 0.10
        self.max_aspect_ratio = 10.0
        self.max_dominant_color_ratio = 0.95
        self.min_std_dev = 10
        self.max_images_per_doc = 1000

        # Skip small images that are likely going to add unnecessary noise
        self.small_image_max_width = 160
        self.small_image_max_height = 160
        self.small_image_max_bytes = 3072

    def _is_image_useful(self, image_bytes: bytes, width: int, height: int, image_name: str) -> bool:
        """
        Applies a series of filters to determine if an image is worth processing.
        """
        # 1. Size-based filters
        if width < self.min_image_width or height < self.min_image_height:
            logger.info(f"  - Skipping {image_name}: Too small ({width}x{height})")
            return False

        if len(image_bytes) < self.min_image_bytes:
            logger.info(f"  - Skipping {image_name}: File size too small ({humanize.naturalsize(len(image_bytes))})")
            return False

        if height > 0:
            aspect_ratio = width / height
            if not (self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio):
                logger.info(f"  - Skipping {image_name}: Extreme aspect ratio ({aspect_ratio:.2f})")
                return False

        # These are typically icons, logos, or decorative elements
        if (
            width <= self.small_image_max_width
            and height <= self.small_image_max_height
            and len(image_bytes) <= self.small_image_max_bytes
        ):
            logger.info(
                f"  - Skipping {image_name}: Small image ({width}x{height}, {humanize.naturalsize(len(image_bytes))})"
            )
            return False

        # 2. Content-based filters
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                # Low content check (std dev) - fast and effective for uniform images
                # Grayscale images with low variance are likely to be uniform color blocks or simple lines.
                gray = img.convert("L")
                gray_array = np.array(gray)
                std_dev = np.std(gray_array)
                if std_dev < self.min_std_dev:
                    logger.info(f"  - Skipping {image_name}: Low content/variance (std dev: {std_dev:.2f})")
                    return False

                # Dominant color check - more robust for single-color blocks
                # To check for dominant colors, we resize the image to a thumbnail (for performance),
                # get the color palette, and calculate the ratio of the most frequent color.
                thumb = img.copy()
                thumb.thumbnail((100, 100), Image.Resampling.LANCZOS)
                colors = thumb.convert("RGB").getcolors(maxcolors=256 * 256)
                if colors:
                    # Sort by count (descending) to find the most dominant color
                    colors.sort(key=lambda x: x[0], reverse=True)
                    dominant_pixel_count = colors[0][0]
                    total_pixels = thumb.width * thumb.height
                    dominant_color_ratio = dominant_pixel_count / total_pixels
                    if dominant_color_ratio > self.max_dominant_color_ratio:
                        logger.info(f"  - Skipping {image_name}: Mostly one color (ratio: {dominant_color_ratio:.2f})")
                        return False

        except Exception as e:
            logger.warning(f"  - Could not analyze content for {image_name}, skipping filters: {e}")

        return True

    def _rects_are_adjacent(self, rect1: fitz.Rect, rect2: fitz.Rect, tolerance: int = 5) -> bool:
        """
        Check if two rectangles are adjacent within tolerance.

        A fitz.Rect is defined by (x0, y0, x1, y1), where:
        - (x0, y0) is the top-left corner.
        - (x1, y1) is the bottom-right corner.
        """
        # Horizontal adjacency: check for close x-coordinates and vertical overlap.
        if (abs(rect1.x1 - rect2.x0) <= tolerance or abs(rect2.x1 - rect1.x0) <= tolerance) and not (
            rect1.y1 < rect2.y0 or rect2.y1 < rect1.y0
        ):  # Ensure vertical overlap
            return True

        # Vertical adjacency: check for close y-coordinates and horizontal overlap.
        if (abs(rect1.y1 - rect2.y0) <= tolerance or abs(rect2.y1 - rect1.y0) <= tolerance) and not (
            rect1.x1 < rect2.x0 or rect2.x1 < rect1.x0
        ):  # Ensure horizontal overlap
            return True

        return False

    def _merge_spatial_images(self, doc: fitz.Document, xref_list: list[int], page: fitz.Page) -> dict[str, Any] | None:
        """
        Merge spatially adjacent images into one.

        Uses PyMuPDF pixmap operations to combine multiple image parts that appear
        to be fragments of a single logical image.

        References:
        - PyMuPDF docs: "How to Extract Images: PDF Documents"
          https://pymupdf.readthedocs.io/en/latest/recipes-images.html#how-to-extract-images-pdf-documents
        - PyMuPDF docs: "How to Use Pixmaps: Gluing Images"
          https://pymupdf.readthedocs.io/en/latest/recipes-images.html#how-to-use-pixmaps-gluing-images
        """
        try:
            # Get rectangles and images for all parts
            parts = []
            for xref in xref_list:
                try:
                    base_image = doc.extract_image(xref)
                    rects = page.get_image_rects(xref)
                    if rects:
                        pix = fitz.Pixmap(base_image["image"])
                        parts.append(
                            {
                                "xref": xref,
                                "page_rect": rects[0],  # Position on page
                                "pixmap": pix,
                                "width": base_image["width"],  # Actual image dimensions
                                "height": base_image["height"],
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to process xref {xref} for spatial merge: {e}")

            if len(parts) < 2:
                return None

            # Determine stacking direction and create canvas
            page_rects = [part["page_rect"] for part in parts]
            # Check if all image parts are aligned vertically by comparing their x-coordinates.
            # A small tolerance of 5 pixels accounts for minor alignment variations.
            if all(abs(rect.x0 - page_rects[0].x0) < 5 for rect in page_rects):
                # Vertical stacking (same x position)
                parts.sort(key=lambda p: p["page_rect"].y0)  # Sort top to bottom

                total_width = max(part["width"] for part in parts)
                total_height = sum(part["height"] for part in parts)

                # Create canvas and stack vertically
                first_pixmap = parts[0]["pixmap"]
                combined_pix = fitz.Pixmap(
                    first_pixmap.colorspace,
                    (0, 0, total_width, total_height),
                    first_pixmap.alpha,
                )

                current_y = 0
                for part in parts:
                    part["pixmap"].set_origin(0, current_y)
                    combined_pix.copy(part["pixmap"], part["pixmap"].irect)
                    current_y += part["height"]

            else:
                # Horizontal stacking (same y position)
                parts.sort(key=lambda p: p["page_rect"].x0)  # Sort left to right

                total_width = sum(part["width"] for part in parts)
                total_height = max(part["height"] for part in parts)

                # Create canvas and stack horizontally
                first_pixmap = parts[0]["pixmap"]
                combined_pix = fitz.Pixmap(
                    first_pixmap.colorspace,
                    (0, 0, total_width, total_height),
                    first_pixmap.alpha,
                )

                current_x = 0
                for part in parts:
                    part["pixmap"].set_origin(current_x, 0)
                    combined_pix.copy(part["pixmap"], part["pixmap"].irect)
                    current_x += part["width"]

            # Convert to bytes
            # PNG is chosen as the output format because it supports transparency (alpha channels),
            # which is essential for merged images, especially those that started with masks.
            combined_bytes = combined_pix.tobytes("png")

            return {
                "bytes": combined_bytes,
                "format": "png",
                "width": total_width,
                "height": total_height,
                "is_combined": True,
                "parts": xref_list,
            }

        except Exception as e:
            logger.warning(f"Failed to merge spatial images {xref_list}: {e}")
            return None

    def _detect_and_merge_split_images(self, doc: fitz.Document, page: fitz.Page) -> dict[int, Any]:
        """
        Detect both mask-based and spatial splits, return merged versions.

        Handles two types of image splits:
        1. Mask-based: Images with separate alpha channels (transparency masks)
        2. Spatial: Adjacent image fragments that should be combined

        References:
        - PyMuPDF docs: "How to Handle Image Masks"
          https://pymupdf.readthedocs.io/en/latest/recipes-images.html#how-to-handle-image-masks
        - PyMuPDF docs: "How to Extract Images: PDF Documents"
          https://pymupdf.readthedocs.io/en/latest/recipes-images.html#how-to-extract-images-pdf-documents
        """
        image_groups: dict[int, Any] = {}

        # First pass: Handle mask-based splits and collect all images
        all_images = []

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            smask = img_info[1] if len(img_info) > 1 else 0

            if smask > 0:
                # smask > 0 indicates a separate alpha channel (transparency mask).
                # We combine the base image with its mask to reconstruct the full image.
                try:
                    base_image = doc.extract_image(xref)
                    mask_image = doc.extract_image(smask)

                    # Create combined image using PyMuPDF
                    pix1 = fitz.Pixmap(base_image["image"])
                    mask = fitz.Pixmap(mask_image["image"])
                    combined_pix = fitz.Pixmap(pix1, mask)

                    # Convert to PNG bytes
                    combined_bytes = combined_pix.tobytes("png")

                    # Store the masked image for spatial analysis
                    image_groups[xref] = {
                        "bytes": combined_bytes,
                        "format": "png",
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "is_combined": True,
                        "pixmap": combined_pix,
                        "parts": [xref, smask],
                    }
                    image_groups[smask] = "skip"  # Mark the mask to be skipped, as it has been merged.

                    all_images.append(xref)
                    logger.info(f"Combined image {xref} with mask {smask}")

                except Exception as e:
                    logger.warning(f"Failed to combine image {xref} with mask {smask}: {e}")
                    # Fall back to processing the base image normally
                    base_image = doc.extract_image(xref)
                    image_groups[xref] = {
                        "bytes": base_image["image"],
                        "format": base_image["ext"],
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "is_combined": False,
                    }
                    all_images.append(xref)

            elif xref not in image_groups:
                # Regular image without mask
                base_image = doc.extract_image(xref)
                image_groups[xref] = {
                    "bytes": base_image["image"],
                    "format": base_image["ext"],
                    "width": base_image["width"],
                    "height": base_image["height"],
                    "is_combined": False,
                }
                all_images.append(xref)

        # Second pass: Detect spatial splits among the processed images
        # This part of the method treats images on the page as nodes in a graph.
        # An edge is created between two nodes if their corresponding images are
        # spatially adjacent. We then find the connected components of this graph.
        # Each component with more than one node represents a single logical image
        # that has been split into multiple pieces.

        # Step 1: Cache the bounding boxes (rects) of all images on the page
        # to avoid repeated calls to page.get_image_rects().
        rects_cache = {}
        for xref in all_images:
            if image_groups.get(xref) == "skip":
                continue
            try:
                rects = page.get_image_rects(xref)
                if rects:
                    rects_cache[xref] = rects[0]
            except Exception as e:
                logger.warning(f"Could not get rect for xref {xref}: {e}")

        # Step 2: Build the adjacency list for the graph. Two images are
        # connected if their rectangles are adjacent.
        adj: dict[int, list[int]] = {xref: [] for xref in rects_cache}
        unprocessed_images = list(rects_cache.keys())

        for i, xref1 in enumerate(unprocessed_images):
            for xref2 in unprocessed_images[i + 1 :]:
                rect1 = rects_cache[xref1]
                rect2 = rects_cache[xref2]
                if self._rects_are_adjacent(rect1, rect2, tolerance=5):
                    adj[xref1].append(xref2)
                    adj[xref2].append(xref1)

        # Step 3: Find all connected components in the graph using a Breadth-First
        # Search (BFS). Each component is a group of adjacent images.
        processed_xrefs = set()
        for xref in unprocessed_images:
            if xref in processed_xrefs:
                continue

            group = []
            q = [xref]
            processed_xrefs.add(xref)
            head = 0
            while head < len(q):
                current_xref = q[head]
                head += 1
                group.append(current_xref)

                for neighbor in adj.get(current_xref, []):
                    if neighbor not in processed_xrefs:
                        processed_xrefs.add(neighbor)
                        q.append(neighbor)

            # Step 4: If a component (group) contains more than one image,
            # merge them into a single image.
            if len(group) > 1:
                try:
                    logger.info(f"Found adjacent image group: {group}")
                    merged_image = self._merge_spatial_images(doc, group, page)
                    if merged_image:
                        primary_xref = group[0]
                        image_groups[primary_xref] = merged_image

                        for part_xref in group[1:]:
                            image_groups[part_xref] = "skip"

                        logger.info(f"Successfully merged spatial group: {group}")
                except Exception as e:
                    logger.warning(f"Failed to merge spatial group {group}: {e}")

        return image_groups

    def process_image_batch(
        self,
        image_batch: list[dict[str, Any]],
        collection_name: str,
        ai_client: "AIPDFBackend",
    ) -> list[dict[str, Any]]:
        """Process a batch of images: describe them and upload to Wagtail."""
        if not image_batch:
            return []

        logger.info(f"  Processing batch of {len(image_batch)} images...")

        # Get descriptions for all images in the batch
        descriptions = ai_client.describe_images_batch(image_batch)

        # Upload each image with its description
        results = []
        for img_data, description in zip(image_batch, descriptions, strict=True):
            try:
                image_name = f"page_{img_data['page_num']}_img_{img_data['img_index']}.{img_data['format']}"

                # Skip decorative images
                if description.upper() == "DECORATIVE":
                    logger.info(f"  - Skipping decorative image: {image_name}")
                    continue

                # Upload the image with the generated description
                image_url = add_image_to_wagtail_collection(
                    image_data=img_data["bytes"],
                    image_name=image_name,
                    collection_name=collection_name,
                    title=image_name,  # Keep original filename as title
                    description=description,  # Use AI-generated description
                )

                # Add to results
                result = {
                    "page": img_data["page_num"],
                    "image_name": image_name,
                    "description": description,
                    "url": image_url,
                }
                results.append(result)

                logger.info(
                    "Uploaded & described: %s - %s",
                    image_name,
                    (description[:100] + "..." if len(description) > 100 else description),
                )

            except Exception as e:
                logger.error(f"  ✗ Failed to upload image on page {img_data['page_num']}: {e}")

        return results

    def extract_and_upload_images(
        self, pdf_bytes: bytes, collection_name: str, ai_client: "AIPDFBackend"
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Extracts images using pyMuPDF (fitz), uploads them with AI-generated descriptions, and creates an image report.
        Includes detection and merging of split images.
        Returns the original PDF bytes unchanged, along with an image report.

        Uses PyMuPDF's image extraction capabilities to find and process embedded images.
        Applies filtering to skip decorative or low-quality images before processing.

        References:
        - PyMuPDF docs: "How to Extract Images: PDF Documents"
          https://pymupdf.readthedocs.io/en/latest/recipes-images.html#how-to-extract-images-pdf-documents
        - PyMuPDF docs: "How to Handle Image Masks"
          https://pymupdf.readthedocs.io/en/latest/recipes-images.html#how-to-handle-image-masks
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # First, do a quick count of all images to check against the threshold
        total_images_found = sum(len(page.get_images(full=True)) for page in doc)

        if total_images_found > self.max_images_per_doc:
            logger.warning(
                f"Skipping image processing for document: Found {total_images_found} images, "
                f"exceeding threshold of {self.max_images_per_doc}."
            )
            doc.close()
            return [], 0

        image_report = []
        images_processed_count = 0
        all_images = []  # Collect all images first
        skipped_images_count = 0
        combined_images_count = 0

        logger.info("\nScanning for images to upload and describe...")

        # First pass: Extract and filter all image data with split detection
        for page in doc:
            # PyMuPDF pages are 0-indexed, so add 1 for human-readable page numbers.
            page_num = page.number + 1

            # Detect and merge split images for this page
            image_groups = self._detect_and_merge_split_images(doc, page)

            img_index = 0
            for xref, image_data in image_groups.items():
                if image_data == "skip":
                    continue  # Skip mask images that were already combined

                try:
                    image_bytes = image_data["bytes"]
                    width, height = image_data["width"], image_data["height"]
                    image_format = image_data["format"]
                    is_combined = image_data["is_combined"]

                    # Create descriptive filename
                    if is_combined:
                        image_name = f"page_{page_num}_img_{img_index}_combined.{image_format}"
                        combined_images_count += 1
                    else:
                        image_name = f"page_{page_num}_img_{img_index}.{image_format}"

                    # Filter out low-value images before processing
                    if not self._is_image_useful(image_bytes, width, height, image_name):
                        skipped_images_count += 1
                        img_index += 1
                        continue

                    all_images.append(
                        {
                            "bytes": image_bytes,
                            "format": image_format,
                            "page_num": page_num,
                            "img_index": img_index,
                            "xref": xref,
                            "is_combined": is_combined,
                        }
                    )
                    img_index += 1

                except Exception as e:
                    logger.error(f"Failed to process image xref {xref} on page {page_num}: {e}")

        doc.close()

        if total_images_found > 0:
            logger.info(
                f"Found {total_images_found} images. "
                f"Combined {combined_images_count} split images. "
                f"Skipped {skipped_images_count} low-value images."
            )

        logger.info(f"Processing {len(all_images)} useful images in batches...")

        # Second pass: Process images in batches using threading
        # Use a thread pool to process image batches in parallel, speeding up I/O-bound tasks
        # like AI API calls and database uploads.
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Split images into batches
            batches = [all_images[i : i + self.batch_size] for i in range(0, len(all_images), self.batch_size)]

            # Submit batch processing tasks
            future_to_batch = {
                executor.submit(self.process_image_batch, batch, collection_name, ai_client): batch for batch in batches
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_batch):
                future_to_batch[future]
                try:
                    batch_results = future.result()
                    image_report.extend(batch_results)
                    images_processed_count += len(batch_results)
                    logger.info(f"  ✓ Completed processing a batch of {len(batch_results)} images")

                except Exception as e:
                    logger.error(f"  ✗ Failed to process batch: {e}")

        return image_report, images_processed_count

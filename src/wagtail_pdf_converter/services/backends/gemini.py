import logging

from http import HTTPStatus
from threading import Lock
from typing import Any, cast

from google import genai
from google.api_core import exceptions as google_exceptions
from google.genai import errors as google_genai_errors
from google.genai import types
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ...conf import settings as conf_settings
from ...utils import get_mime_type_from_bytes
from ..base import PDFConversionError
from .base import AIPDFBackend


logger = logging.getLogger(__name__)


class GeminiBackend(AIPDFBackend):
    """
    Handles Gemini AI service interactions for image description and content conversion.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the Gemini client with config."""
        self.api_key = config.get("API_KEY", "")
        if not self.api_key:
            raise PDFConversionError("API key must be provided in backend configuration.")

        self.image_model = cast(str, config.get("IMAGE_MODEL", "gemini-2.5-flash"))
        self.conversion_model = cast(str, config.get("CONVERSION_MODEL", "gemini-2.5-flash"))
        self._client_lock = Lock()  # Thread safety for API client

        try:
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            logger.exception("API client initialization error: %s", e)
            raise PDFConversionError(f"API client initialization error: {e}") from e

    def describe_images_batch(self, image_batch: list[dict[str, Any]]) -> list[str]:
        """
        Describe multiple images in a single API call for better efficiency.

        Args:
            image_batch: List of dicts with keys: 'bytes', 'format', 'page_num', 'img_index'

        Returns:
            List of descriptions in the same order as input batch
        """
        if not image_batch:
            return []

        # Prepare content for batch processing
        contents: list[str | types.Part] = [conf_settings.PROMPTS["IMAGE_BATCH_DESCRIPTION"]]

        # Add all images to the content
        for _, img_data in enumerate(image_batch):
            mime_type = get_mime_type_from_bytes(img_data["bytes"])
            part = types.Part.from_bytes(data=img_data["bytes"], mime_type=mime_type)
            contents.append(part)

        try:
            with self._client_lock:
                response = self.client.models.generate_content(
                    model=self.image_model,
                    contents=contents,  # type: ignore[arg-type]
                )

            if not response or not response.text:
                logger.warning(f"No description generated for batch of {len(image_batch)} images")
                return [f"Image from page {img['page_num']}" for img in image_batch]

            # Split the response by separator
            descriptions = response.text.strip().split("---SEPARATOR---")

            # Clean up descriptions and ensure we have the right number
            descriptions = [desc.strip() for desc in descriptions if desc.strip()]

            # If we don't get the expected number of descriptions, fall back to individual processing
            if len(descriptions) != len(image_batch):
                logger.warning(
                    f"Expected {len(image_batch)} descriptions but got {len(descriptions)}. "
                    "Falling back to individual processing."
                )
                return self._describe_images_individually(image_batch)

            # Process each description to handle prefixes
            processed_descriptions = []
            for desc in descriptions:
                if desc.upper().startswith("DECORATIVE"):
                    processed_descriptions.append("DECORATIVE")
                elif desc.upper().startswith("MEANINGFUL:"):
                    processed_descriptions.append(desc[11:].strip())
                else:
                    processed_descriptions.append(desc)  # Assume meaningful if no prefix

            return processed_descriptions

        except Exception as e:
            logger.error(f"Failed to describe batch of {len(image_batch)} images: {e}")
            # Fall back to individual processing
            return self._describe_images_individually(image_batch)

    def _describe_images_individually(self, image_batch: list[dict[str, Any]]) -> list[str]:
        """Fall back method to describe images one by one."""
        descriptions = []
        for img_data in image_batch:
            try:
                description = self.describe_single_image(
                    img_data["bytes"],
                    img_data["format"],
                    img_data["page_num"],
                    img_data["img_index"],
                )
                descriptions.append(description)
            except Exception as e:
                logger.error(f"Failed to describe individual image on page {img_data['page_num']}: {e}")
                descriptions.append(f"Image from page {img_data['page_num']}")
        return descriptions

    def describe_single_image(self, image_bytes: bytes, image_format: str, page_num: int, img_index: int) -> str:
        """Describe a single image with AI API"""
        mime_type = get_mime_type_from_bytes(image_bytes)

        try:
            image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            contents_list = [
                conf_settings.PROMPTS["IMAGE_SINGLE_DESCRIPTION"],
                image_part,
            ]
            with self._client_lock:
                response = self.client.models.generate_content(
                    model=self.image_model,
                    contents=contents_list,
                )

            if not response or not response.text:
                logger.warning(f"No description generated for page {page_num} img {img_index}")
                return f"Image from page {page_num}"

            result = response.text.strip()

            if result.upper().startswith("DECORATIVE"):
                return "DECORATIVE"
            elif result.upper().startswith("MEANINGFUL:"):
                return result[11:].strip()  # Remove "MEANINGFUL: " prefix
            else:
                return result  # Assume it's meaningful

        except Exception as e:
            logger.error(f"Failed to describe image on page {page_num}: {e}")
            return f"Image from page {page_num}"

    def _format_image_report(self, image_report: list[dict[str, Any]]) -> str:
        """Format the image report as a readable string for the prompt."""
        if not image_report:
            return "No images were found in this document."

        report_lines = ["EXTRACTED IMAGES:"]
        for img_info in image_report:
            report_lines.append(f"- Page {img_info['page']}: {img_info['description']}")
            report_lines.append(f"  URL: {img_info['url']}")
            report_lines.append("")

        return "\n".join(report_lines)

    def _get_prompt(self, image_report: str) -> str:
        """
        Returns prompt used to convert PDF to markdown.
        """
        return conf_settings.PROMPTS["PDF_CONVERSION_TEMPLATE"].format(image_report=image_report)

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=120),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(
            (
                google_exceptions.InternalServerError,
                google_exceptions.ResourceExhausted,
                google_exceptions.ServiceUnavailable,
                google_genai_errors.ServerError,
                PDFConversionError,
            )
        ),
    )
    def convert_content_with_retry(self, contents: list[Any]) -> str:
        """Generic content conversion call with error handling and retries."""
        try:
            response = self.client.models.generate_content(model=self.conversion_model, contents=contents)

            if not response:
                logger.warning("API call returned a None response object. Retrying...")
                raise PDFConversionError("API returned None response.")

            if not response.text:
                feedback = getattr(response, "prompt_feedback", None)
                reason = getattr(feedback, "block_reason", None)
                if reason:
                    reason_name = reason.name
                    logger.error(f"API call blocked. Reason: {reason_name}")
                    raise PDFConversionError(f"API call blocked for reason: {reason_name}")
                else:
                    logger.warning("API call returned an empty response with no block reason. Retrying...")
                    raise PDFConversionError("API returned empty response.")
            return response.text.strip()

        except PDFConversionError as e:
            raise e
        except (
            google_exceptions.InternalServerError,
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_genai_errors.ServerError,
        ) as e:
            logger.warning(f"API call failed with {type(e).__name__}. Retrying...")
            raise e
        except google_genai_errors.ClientError as e:
            # Handle 4xx client errors
            # convert 429 errors to ResourceExhausted so they're retried
            if e.code == HTTPStatus.TOO_MANY_REQUESTS:
                logger.warning("Rate limit hit (429). Retrying...")
                raise google_exceptions.ResourceExhausted("Rate limit exceeded (429)") from e
            # Other 4xx errors (400, 401, 403, 404, etc.) shouldn't be retried
            logger.exception("Client error: %s %s. %s", e.code, e.status, e.message)
            raise PDFConversionError(f"Client error: {e.code} {e.status}. {e.message}") from e
        except Exception as e:
            logger.exception(f"An unexpected error occurred during API conversion: {e}")
            raise PDFConversionError(f"An unexpected API error occurred: {e}") from e

    def format_image_report_and_get_prompt(self, image_report: list[dict[str, Any]]) -> str:
        """Format image report and return the full conversion prompt."""
        image_report_text = self._format_image_report(image_report)
        return self._get_prompt(image_report_text)

    def convert_chunk_with_continuation(
        self,
        chunk_bytes: bytes,
        base_prompt: str,
        previous_chunk_markdown: str | None = None,
        chunk_number: int = 1,
        total_chunks: int = 1,
    ) -> str:
        """
        Converts a PDF chunk to markdown, using the end of the previous
        chunk's markdown to provide context for continuation.
        """
        contents: list[Any] = []
        if previous_chunk_markdown:
            # Get more context - last 15 lines or 500 characters, whichever is more
            lines = previous_chunk_markdown.strip().splitlines()

            # Take last 15 lines or enough to get at least 500 characters
            context_lines: list[str] = []
            char_count = 0
            for line in reversed(lines[-15:]):
                context_lines.insert(0, line)
                char_count += len(line)
                if char_count >= 500 and len(context_lines) >= 5:
                    break

            # If we're in the middle of a table, include the table header
            context_text = "\n".join(context_lines)
            if "|" in context_text and not context_text.strip().startswith("|"):
                # Look for table header in more lines
                for i in range(len(lines) - 20, max(0, len(lines) - 50), -1):
                    if i >= 0 and lines[i].strip().startswith("|") and "---" in lines[i + 1 : i + 3]:
                        # Found table header, include it
                        context_lines = lines[i : len(lines)]
                        break

            last_lines = "\n".join(context_lines)
            continuation_prompt = conf_settings.PROMPTS["MARKDOWN_CONTINUATION"].format(
                previous_chunk_markdown_end=last_lines,
                chunk_number=chunk_number,
                total_chunks=total_chunks,
            )
            contents.append(continuation_prompt)

        contents.append(base_prompt)
        contents.append(types.Part.from_bytes(data=chunk_bytes, mime_type="application/pdf"))

        return self.convert_content_with_retry(contents)

    def convert_single_pass(self, pdf_bytes: bytes, prompt: str) -> str:
        """
        Convert a full PDF in a single API call for Gemini.
        """
        return self.convert_content_with_retry(
            [
                prompt,
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type="application/pdf",
                ),
            ]
        )

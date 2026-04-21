from abc import ABC, abstractmethod
from typing import Any


class AIPDFBackend(ABC):
    """
    Abstract base class for AI backends used by the PDF converter.
    """

    @abstractmethod
    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize the backend with a configuration dictionary.
        """
        pass

    @abstractmethod
    def describe_images_batch(self, image_batch: list[dict[str, Any]]) -> list[str]:
        """
        Describe multiple images in a single API call for better efficiency.

        Args:
            image_batch: List of dicts with keys: 'bytes', 'format', 'page_num', 'img_index'

        Returns:
            List of descriptions in the same order as input batch
        """
        pass

    @abstractmethod
    def describe_single_image(self, image_bytes: bytes, image_format: str, page_num: int, img_index: int) -> str:
        """
        Describe a single image.
        """
        pass

    @abstractmethod
    def format_image_report_and_get_prompt(self, image_report: list[dict[str, Any]]) -> str:
        """
        Format image report and return the full conversion prompt.
        """
        pass

    @abstractmethod
    def convert_content_with_retry(self, contents: list[Any]) -> str:
        """
        Generic content conversion call with error handling and retries.
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def convert_single_pass(self, pdf_bytes: bytes, prompt: str) -> str:
        """
        Convert a full PDF in a single API call.
        """
        pass

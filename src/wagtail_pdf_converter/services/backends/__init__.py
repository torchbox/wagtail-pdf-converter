from typing import cast

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from ...conf import settings as conf_settings
from .base import AIPDFBackend


__all__ = ["get_ai_backend", "AIPDFBackend"]


def get_ai_backend(alias: str = "default") -> AIPDFBackend:
    """
    Returns an instance of the AI backend for the given alias.
    """
    backends = conf_settings.AI_BACKENDS

    if alias not in backends:
        raise ImproperlyConfigured(f"AI backend '{alias}' not found in WAGTAIL_PDF_CONVERTER['AI_BACKENDS'].")

    backend_config = backends[alias]

    if "CLASS" not in backend_config:
        raise ImproperlyConfigured(f"AI backend '{alias}' is missing the 'CLASS' setting.")

    try:
        backend_cls = cast(type[AIPDFBackend], import_string(backend_config["CLASS"]))
    except ImportError as e:
        raise ImproperlyConfigured(f"Could not import AI backend class '{backend_config['CLASS']}': {e}") from e

    config = backend_config.get("CONFIG", {})
    return backend_cls(config=config)

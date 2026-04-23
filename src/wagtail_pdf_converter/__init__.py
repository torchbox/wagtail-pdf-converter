import re


__version__ = "0.1.0rc1"


def _get_version_tuple(version_string: str) -> tuple[int, ...]:
    """Extract numeric version components, ignoring pre-release suffixes.

    Handles both PEP 440 (e.g., "1.2.3a0") and semver (e.g., "1.2.3-alpha.0") formats.
    See: https://peps.python.org/pep-0440/

    Args:
        version_string: Version string in any common format

    Returns:
        Tuple of integers representing (major, minor, patch, ...)

    Examples:
        >>> _get_version_tuple("0.2.1")
        (0, 2, 1)
        >>> _get_version_tuple("0.2.1-rc1")
        (0, 2, 1)
        >>> _get_version_tuple("1.2.3a0")
        (1, 2, 3)
        >>> _get_version_tuple("v1.2.3")
        (1, 2, 3)
    """
    # Remove 'v' prefix if it exists
    if version_string.startswith("v"):
        version_string = version_string[1:]

    # Extract only the numeric parts (e.g., "0.2.1-rc1" -> "0.2.1")
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", version_string)
    if match:
        return tuple(int(x) for x in match.groups() if x is not None)
    # Fallback for simpler versions
    return tuple(int(x) for x in version_string.split(".") if x.isdigit())


VERSION = _get_version_tuple(__version__)

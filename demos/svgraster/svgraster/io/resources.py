"""Loading referenced resources: ``data:`` URIs and local files (remote URLs are refused)."""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote_to_bytes

REMOTE_SCHEMES = ("http:", "https:", "ftp:")
MAX_RESOURCE_BYTES = 256 * 1024 * 1024


class ResourceError(OSError):
    """A referenced image, font or document could not be loaded."""


@dataclass(frozen=True)
class Resource:
    """Loaded bytes with their media type (from the URI or the file suffix) and origin."""

    data: bytes
    media_type: str
    path: Path | None = None
    fragment: str | None = None


SUFFIX_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".jpe": "image/jpeg",
    ".svg": "image/svg+xml", ".svgz": "image/svg+xml", ".ttf": "font/ttf", ".otf": "font/otf",
    ".ttc": "font/collection",
}


def sniff(data: bytes) -> str:
    """The media type implied by the leading bytes, or ``application/octet-stream``."""
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf"):
        return "font/ttf"
    head = data[:512].lstrip()
    if head.startswith(b"<") or data.startswith(b"\x1f\x8b"):
        return "image/svg+xml"
    return "application/octet-stream"


def parse_data_uri(uri: str) -> Resource:
    """Decode a ``data:[type][;base64],payload`` URI."""
    try:
        header, payload = uri[5:].split(",", 1)
    except ValueError:
        raise ResourceError("malformed data URI (no comma)") from None
    parts = [p.strip() for p in header.split(";")]
    media = parts[0].lower() if parts and parts[0] else ""
    if "base64" in (p.lower() for p in parts[1:]):
        try:
            data = base64.b64decode("".join(payload.split()), validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ResourceError(f"invalid base64 in data URI: {exc}") from None
    else:
        data = unquote_to_bytes(payload)
    return Resource(data, media or sniff(data))


def load(href: str, document) -> Resource:
    """Load ``href`` relative to ``document.base_dir``; the ``#fragment`` is kept separately."""
    href = href.strip()
    if href.startswith("data:"):
        return parse_data_uri(href)
    if href.lower().startswith(REMOTE_SCHEMES):
        raise ResourceError(f"remote resources are not fetched: {href}")
    fragment = None
    if "#" in href:
        href, fragment = href.split("#", 1)
    path = document.resolve(href)
    try:
        if path.stat().st_size > MAX_RESOURCE_BYTES:
            raise ResourceError(f"resource too large: {path}")
        data = path.read_bytes()
    except OSError as exc:
        if isinstance(exc, ResourceError):
            raise
        raise ResourceError(f"cannot read {path}: {exc.strerror or exc}") from None
    media = SUFFIX_TYPES.get(path.suffix.lower()) or sniff(data)
    return Resource(data, media, path, fragment)

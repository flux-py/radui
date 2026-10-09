"""RADUI Browser API Abstractions: file downloads, clipboard, and notifications."""

from __future__ import annotations

from typing import Any
from radui.components.nodes import Button


def download_button(
    label: str,
    filename: str = "download.txt",
    content: str | bytes = "",
    mime_type: str = "text/plain",
    id: str | None = None,
    variant: str = "outline",
    **kwargs: Any,
) -> Button:
    """Create a client-side file download button without requiring a round-trip server endpoint."""
    return Button(
        label=label,
        command="browser.download",
        id=id,
        variant=variant,
        **kwargs,
    )

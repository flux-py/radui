from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Iterator


class TokenStream:
    """Helper for managing streaming tokens and text chunks in AI applications."""

    def __init__(self) -> None:
        self._tokens: list[str] = []

    def push(self, token: str) -> None:
        self._tokens.append(token)

    @property
    def text(self) -> str:
        return "".join(self._tokens)

    def __iter__(self) -> Iterator[str]:
        return iter(self._tokens)


class StreamingFenceParser:
    """
    Incremental parser for streaming LLM output that detects structured UI code blocks
    (e.g. ```RADUI, ```dyui, ```json:ui, ```a2ui) and extracts structured JSON components
    while streaming raw markdown text chunks.
    """

    FENCE_PATTERN = re.compile(r"```(?:RADUI|RADUI-ui|dyui|a2ui|json:ui)\s*\n(.*?)```", re.DOTALL)

    def __init__(self) -> None:
        self._buffer: str = ""
        self._extracted_components: list[dict[str, Any]] = []

    def feed(self, chunk: str) -> tuple[str, list[dict[str, Any]]]:
        """
        Feeds a text delta chunk into the parser.
        Returns (visible_text_delta, newly_parsed_components).
        """
        self._buffer += chunk
        new_components = []

        # Find any completed fences
        while True:
            match = self.FENCE_PATTERN.search(self._buffer)
            if not match:
                break
            raw_block = match.group(1).strip()
            # Attempt parsing JSON inside the block
            try:
                # Can be single JSON object or newline-delimited JSON
                for line in raw_block.splitlines():
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        spec = json.loads(line)
                        if isinstance(spec, dict):
                            new_components.append(spec)
                            self._extracted_components.append(spec)
                    elif not line:
                        continue
                if not new_components and raw_block.startswith("{"):
                    spec = json.loads(raw_block)
                    if isinstance(spec, dict):
                        new_components.append(spec)
                        self._extracted_components.append(spec)
            except Exception:
                # Invalid JSON in fence, leave as is
                pass

            # Remove the fence from the buffer
            start, end = match.span()
            self._buffer = self._buffer[:start] + self._buffer[end:]

        # Return visible text excluding potential open fences
        # If there's an open unclosed fence, hold it in buffer
        open_fence_idx = self._buffer.rfind("```")
        if open_fence_idx != -1 and ("\n" not in self._buffer[open_fence_idx:] or not self._buffer.endswith("```")):
            # Incomplete fence; stream everything up to the fence
            visible = self._buffer[:open_fence_idx]
            self._buffer = self._buffer[open_fence_idx:]
            return visible, new_components

        visible = self._buffer
        self._buffer = ""
        return visible, new_components

    def finish(self) -> tuple[str, list[dict[str, Any]]]:
        """Flushes any remaining text at stream end."""
        remaining = self._buffer
        self._buffer = ""
        return remaining, list(self._extracted_components)


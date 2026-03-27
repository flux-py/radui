from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Theme:
    """Design tokens and theming configuration for RADUI applications."""

    name: str = "default"
    mode: Literal["light", "dark", "system"] = "system"
    direction: Literal["ltr", "rtl"] = "ltr"
    primary: str = "#2563eb"
    primary_hover: str = "#1d4ed8"
    primary_subtle: str = "#eff6ff"
    bg: str = "#f8fafc"
    surface: str = "#ffffff"
    surface_alt: str = "#f1f5f9"
    text: str = "#0f172a"
    text_muted: str = "#64748b"
    border: str = "#e2e8f0"
    border_strong: str = "#cbd5e1"
    radius: str = "8px"
    font: str = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    font_mono: str = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
    custom_css: str = ""

    def to_css(self) -> str:
        """Generate CSS custom properties for the theme."""
        selector = f'[data-theme="{self.name}"]' if self.name != "default" else ":root"
        lines = [
            f"{selector} {{",
            f"  --gx-primary: {self.primary};",
            f"  --gx-primary-hover: {self.primary_hover};",
            f"  --gx-primary-subtle: {self.primary_subtle};",
            f"  --gx-bg: {self.bg};",
            f"  --gx-surface: {self.surface};",
            f"  --gx-surface-alt: {self.surface_alt};",
            f"  --gx-text: {self.text};",
            f"  --gx-text-muted: {self.text_muted};",
            f"  --gx-border: {self.border};",
            f"  --gx-border-strong: {self.border_strong};",
            f"  --gx-radius: {self.radius};",
            f"  --gx-font: {self.font};",
            f"  --gx-font-mono: {self.font_mono};",
            f"  direction: {self.direction};",
            "}",
        ]
        if self.custom_css:
            lines.append(self.custom_css)
        return "\n".join(lines)

    @classmethod
    def dark(cls) -> Theme:
        return cls(
            name="dark",
            mode="dark",
            primary="#3b82f6",
            primary_hover="#60a5fa",
            primary_subtle="#1e293b",
            bg="#0f172a",
            surface="#1e293b",
            surface_alt="#334155",
            text="#f8fafc",
            text_muted="#94a3b8",
            border="#334155",
            border_strong="#475569",
        )

    @classmethod
    def indigo(cls) -> Theme:
        return cls(
            name="indigo",
            primary="#6366f1",
            primary_hover="#4f46e5",
            primary_subtle="#eef2ff",
        )

    @classmethod
    def emerald(cls) -> Theme:
        return cls(
            name="emerald",
            primary="#059669",
            primary_hover="#047857",
            primary_subtle="#ecfdf5",
        )

    @classmethod
    def zinc(cls) -> Theme:
        return cls(
            name="zinc",
            primary="#18181b",
            primary_hover="#27272a",
            primary_subtle="#f4f4f5",
        )

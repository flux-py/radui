from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EasingCurve(StrEnum):
    LINEAR = "linear"
    EASE = "ease"
    EASE_IN = "ease-in"
    EASE_OUT = "ease-out"
    EASE_IN_OUT = "ease-in-out"
    SPRING = "spring"
    ANTICIPATE = "cubic-bezier(0.36, 0, 0.66, -0.56)"
    BACK_OUT = "cubic-bezier(0.34, 1.56, 0.64, 1)"
    SMOOTH = "cubic-bezier(0.16, 1, 0.3, 1)"


@dataclass(frozen=True)
class SpringConfig:
    """Physics-based spring parameters."""

    stiffness: float = 120.0
    damping: float = 14.0
    mass: float = 1.0
    initial_velocity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "spring",
            "stiffness": self.stiffness,
            "damping": self.damping,
            "mass": self.mass,
            "initial_velocity": self.initial_velocity,
        }


@dataclass(frozen=True)
class EaseConfig:
    """Timing and bezier-based easing parameters."""

    curve: str = EasingCurve.SMOOTH.value
    duration: float = 0.35  # seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "ease",
            "curve": self.curve,
            "duration": self.duration,
        }


@dataclass(frozen=True)
class HoverConfig:
    """Micro-interaction configuration triggered on cursor hover."""

    scale: float | None = 1.02
    translate_y: float | None = -2.0  # pixels
    shadow: str | None = "0 10px 25px -5px rgba(0, 0, 0, 0.1)"
    duration: float = 0.2

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {"duration": self.duration}
        if self.scale is not None:
            res["scale"] = self.scale
        if self.translate_y is not None:
            res["translateY"] = self.translate_y
        if self.shadow is not None:
            res["shadow"] = self.shadow
        return res


@dataclass(frozen=True)
class TapConfig:
    """Micro-interaction configuration triggered on pointer press/tap."""

    scale: float = 0.97
    duration: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        return {
            "scale": self.scale,
            "duration": self.duration,
        }


@dataclass(frozen=True)
class MotionConfig:
    """Declarative motion specification for a RADUI component."""

    preset: str = "fade_in"
    initial: dict[str, Any] = field(default_factory=lambda: {"opacity": 0, "transform": "translateY(12px)"})
    animate: dict[str, Any] = field(default_factory=lambda: {"opacity": 1, "transform": "translateY(0px)"})
    exit: dict[str, Any] | None = None
    transition: SpringConfig | EaseConfig = field(default_factory=SpringConfig)
    delay: float = 0.0  # seconds
    duration: float = 0.4  # seconds
    stagger: float = 0.0  # seconds

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "preset": self.preset,
            "initial": self.initial,
            "animate": self.animate,
            "transition": self.transition.to_dict(),
            "delay": self.delay,
            "duration": self.duration,
        }
        if self.exit:
            res["exit"] = self.exit
        if self.stagger > 0:
            res["stagger"] = self.stagger
        return res

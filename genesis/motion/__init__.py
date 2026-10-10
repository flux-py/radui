from __future__ import annotations

from typing import Any

from radui.motion.springs import solve_spring_keyframes
from radui.motion.types import (
    EaseConfig,
    EasingCurve,
    HoverConfig,
    MotionConfig,
    SpringConfig,
    TapConfig,
)


def spring(
    stiffness: float = 120.0,
    damping: float = 14.0,
    mass: float = 1.0,
    initial_velocity: float = 0.0,
) -> SpringConfig:
    """Create a physics spring configuration."""
    return SpringConfig(
        stiffness=stiffness,
        damping=damping,
        mass=mass,
        initial_velocity=initial_velocity,
    )


def ease(
    curve: str = EasingCurve.SMOOTH.value,
    duration: float = 0.35,
) -> EaseConfig:
    """Create a timing and easing configuration."""
    return EaseConfig(curve=curve, duration=duration)


def hover(
    scale: float | None = 1.02,
    translate_y: float | None = -2.0,
    shadow: str | None = "0 10px 25px -5px rgba(0, 0, 0, 0.1)",
    duration: float = 0.2,
) -> HoverConfig:
    """Configure micro-interaction on cursor hover."""
    return HoverConfig(
        scale=scale,
        translate_y=translate_y,
        shadow=shadow,
        duration=duration,
    )


def tap(
    scale: float = 0.97,
    duration: float = 0.1,
) -> TapConfig:
    """Configure micro-interaction on pointer tap/click."""
    return TapConfig(scale=scale, duration=duration)


def enter(
    initial: dict[str, Any] | None = None,
    animate: dict[str, Any] | None = None,
    transition: SpringConfig | EaseConfig | None = None,
    delay: float = 0.0,
    duration: float = 0.4,
    stagger: float = 0.0,
) -> MotionConfig:
    """Create a custom entrance motion configuration."""
    init_props = initial or {"opacity": 0, "transform": "translateY(12px)"}
    anim_props = animate or {"opacity": 1, "transform": "translateY(0px)"}
    trans = transition or SpringConfig()
    return MotionConfig(
        preset="custom",
        initial=init_props,
        animate=anim_props,
        transition=trans,
        delay=delay,
        duration=duration,
        stagger=stagger,
    )


def fade_in(duration: float = 0.35, delay: float = 0.0) -> MotionConfig:
    """Fade-in opacity entrance animation."""
    return MotionConfig(
        preset="fade_in",
        initial={"opacity": 0},
        animate={"opacity": 1},
        transition=EaseConfig(curve=EasingCurve.EASE_OUT.value, duration=duration),
        delay=delay,
        duration=duration,
    )


def slide_up(
    distance: int = 16,
    duration: float = 0.4,
    delay: float = 0.0,
    use_spring: bool = True,
) -> MotionConfig:
    """Slide up with opacity entrance."""
    trans = SpringConfig(damping=16.0, stiffness=140.0) if use_spring else EaseConfig(curve=EasingCurve.SMOOTH.value, duration=duration)
    return MotionConfig(
        preset="slide_up",
        initial={"opacity": 0, "transform": f"translateY({distance}px)"},
        animate={"opacity": 1, "transform": "translateY(0px)"},
        transition=trans,
        delay=delay,
        duration=duration,
    )


def slide_down(
    distance: int = 16,
    duration: float = 0.4,
    delay: float = 0.0,
    use_spring: bool = True,
) -> MotionConfig:
    """Slide down entrance."""
    trans = SpringConfig(damping=16.0, stiffness=140.0) if use_spring else EaseConfig(curve=EasingCurve.SMOOTH.value, duration=duration)
    return MotionConfig(
        preset="slide_down",
        initial={"opacity": 0, "transform": f"translateY(-{distance}px)"},
        animate={"opacity": 1, "transform": "translateY(0px)"},
        transition=trans,
        delay=delay,
        duration=duration,
    )


def scale_up(
    initial_scale: float = 0.92,
    duration: float = 0.4,
    delay: float = 0.0,
    use_spring: bool = True,
) -> MotionConfig:
    """Scale-up entrance with spring."""
    trans = SpringConfig(damping=14.0, stiffness=130.0) if use_spring else EaseConfig(curve=EasingCurve.SMOOTH.value, duration=duration)
    return MotionConfig(
        preset="scale_up",
        initial={"opacity": 0, "transform": f"scale({initial_scale})"},
        animate={"opacity": 1, "transform": "scale(1)"},
        transition=trans,
        delay=delay,
        duration=duration,
    )


def pop(duration: float = 0.35, delay: float = 0.0) -> MotionConfig:
    """Quick punchy pop entrance."""
    return MotionConfig(
        preset="pop",
        initial={"opacity": 0, "transform": "scale(0.85)"},
        animate={"opacity": 1, "transform": "scale(1)"},
        transition=SpringConfig(damping=12.0, stiffness=180.0),
        delay=delay,
        duration=duration,
    )


def pulse() -> MotionConfig:
    """Gentle breathing pulse motion."""
    return MotionConfig(
        preset="pulse",
        initial={"transform": "scale(1)"},
        animate={"transform": "scale(1.04)"},
        transition=EaseConfig(curve=EasingCurve.EASE_IN_OUT.value, duration=1.2),
    )


def stagger(index: int, base: float = 0.04) -> float:
    """Calculate cascaded stagger delay."""
    return max(0.0, index * base)


__all__ = [
    "EaseConfig",
    "EasingCurve",
    "HoverConfig",
    "MotionConfig",
    "SpringConfig",
    "TapConfig",
    "ease",
    "enter",
    "fade_in",
    "hover",
    "pop",
    "pulse",
    "scale_up",
    "slide_down",
    "slide_up",
    "solve_spring_keyframes",
    "spring",
    "stagger",
    "tap",
]

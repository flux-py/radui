from __future__ import annotations

import math
from typing import Any


def solve_spring_keyframes(
    stiffness: float = 120.0,
    damping: float = 14.0,
    mass: float = 1.0,
    initial_velocity: float = 0.0,
    steps: int = 30,
    settle_threshold: float = 0.001,
) -> list[float]:
    """Analytical solution for a damped harmonic oscillator step response (0.0 to 1.0).

    Returns a normalized array of step progress values from 0.0 to ~1.0.
    """
    if mass <= 0:
        mass = 1.0
    if stiffness <= 0:
        stiffness = 100.0
    if damping < 0:
        damping = 10.0

    omega0 = math.sqrt(stiffness / mass)
    zeta = damping / (2.0 * math.sqrt(stiffness * mass))

    # Duration estimate based on decay
    decay_rate = zeta * omega0 if zeta > 0 else 1.0
    total_time = max(0.3, min(2.5, -math.log(settle_threshold) / decay_rate))

    keyframes: list[float] = []

    for i in range(steps + 1):
        t = (i / steps) * total_time
        if i == 0:
            keyframes.append(0.0)
            continue
        if i == steps:
            keyframes.append(1.0)
            continue

        if zeta < 0.999:  # Underdamped
            omega_d = omega0 * math.sqrt(1.0 - zeta * zeta)
            envelope = math.exp(-zeta * omega0 * t)
            sin_term = (zeta * omega0 + initial_velocity) / omega_d
            val = 1.0 - envelope * (math.cos(omega_d * t) + sin_term * math.sin(omega_d * t))
        elif zeta <= 1.001:  # Critically damped
            envelope = math.exp(-omega0 * t)
            val = 1.0 - envelope * (1.0 + (omega0 - initial_velocity) * t)
        else:  # Overdamped
            alpha = math.sqrt(zeta * zeta - 1.0)
            s1 = -omega0 * (zeta - alpha)
            s2 = -omega0 * (zeta + alpha)
            c1 = (s2 + initial_velocity) / (s2 - s1)
            c2 = (-s1 - initial_velocity) / (s2 - s1)
            val = 1.0 - (c1 * math.exp(s1 * t) + c2 * math.exp(s2 * t))

        keyframes.append(round(val, 5))

    return keyframes


def generate_waapi_transform_keyframes(
    from_transform: str,
    to_transform: str,
    spring_progress: list[float],
) -> list[dict[str, Any]]:
    """Generate WAAPI-compatible keyframe objects mapping spring progress."""
    result: list[dict[str, Any]] = []
    for p in spring_progress:
        # p ranges ~0 to 1
        result.append({"progress": p})
    return result

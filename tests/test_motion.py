import json
import pytest
from radui import motion
import radui as gx
from radui.renderers.html import HTMLRenderer


def test_analytical_spring_solver():
    keyframes = motion.solve_spring_keyframes(stiffness=120.0, damping=14.0, mass=1.0, steps=30)
    assert len(keyframes) == 31
    assert keyframes[0] == 0.0
    assert keyframes[-1] == 1.0
    # Damped spring should reach or slightly overshoot near 1.0 before settling
    assert any(k >= 0.9 for k in keyframes)


def test_critically_damped_and_overdamped_springs():
    crit = motion.solve_spring_keyframes(stiffness=100.0, damping=20.0, steps=20)
    assert len(crit) == 21
    assert crit[0] == 0.0
    assert crit[-1] == 1.0

    over = motion.solve_spring_keyframes(stiffness=50.0, damping=30.0, steps=20)
    assert len(over) == 21
    assert over[0] == 0.0
    assert over[-1] == 1.0


def test_motion_presets():
    fi = motion.fade_in(duration=0.5, delay=0.1)
    assert fi.preset == "fade_in"
    assert fi.duration == 0.5
    assert fi.delay == 0.1
    assert fi.initial == {"opacity": 0}
    assert fi.animate == {"opacity": 1}

    su = motion.slide_up(distance=24)
    assert su.preset == "slide_up"
    assert "translateY(24px)" in su.initial["transform"]

    sc = motion.scale_up(initial_scale=0.9)
    assert sc.preset == "scale_up"
    assert "scale(0.9)" in sc.initial["transform"]

    pop_anim = motion.pop()
    assert pop_anim.preset == "pop"

    pulse_anim = motion.pulse()
    assert pulse_anim.preset == "pulse"


def test_stagger_calculation():
    assert motion.stagger(0) == 0.0
    assert motion.stagger(1, base=0.05) == 0.05
    assert motion.stagger(3, base=0.05) == pytest.approx(0.15)


def test_motion_serialization_in_components():
    renderer = HTMLRenderer()

    # Card with motion, hover and tap
    c = gx.card(
        gx.heading("Animated Card"),
        id="animated-card",
        motion=motion.slide_up(distance=20),
        hover=motion.hover(scale=1.03, translate_y=-3.0),
        tap=motion.tap(scale=0.96),
        motion_id="hero-card",
    )
    html = renderer.render_component(c)

    assert 'id="animated-card"' in html
    assert 'data-gx-motion="' in html
    assert 'slide_up' in html
    assert 'data-gx-hover="' in html
    assert '1.03' in html
    assert 'data-gx-tap="' in html
    assert '0.96' in html
    assert 'data-gx-motion-id="hero-card"' in html


def test_metric_card_number_animation():
    renderer = HTMLRenderer()

    metric = gx.metric_card(
        "Active Workflows",
        "1,420",
        id="metric-workflows",
        animate_number=True,
    )
    html = renderer.render_component(metric)

    assert 'data-gx-animate-number="true"' in html
    assert "1,420" in html


def test_grid_stagger_serialization():
    renderer = HTMLRenderer()

    g = gx.grid(
        gx.card(gx.text(value="Card 1")),
        gx.card(gx.text(value="Card 2")),
        stagger_children=0.06,
        id="stagger-grid",
    )
    html = renderer.render_component(g)

    assert 'data-gx-stagger="0.06"' in html

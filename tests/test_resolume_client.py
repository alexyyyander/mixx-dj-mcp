from mixx_dj_mcp.resolume_client import (
    deck_beat_phase,
    deck_visual_energy,
    effect_param_address,
    layer_opacity_address,
)


def test_layer_opacity_address():
    assert layer_opacity_address(2) == "/composition/layers/2/opacity"


def test_effect_param_address():
    assert effect_param_address(2, 1, 3) == "/composition/layers/2/effects/1/params/3/value"


def test_deck_beat_phase_zero_when_no_rate():
    assert deck_beat_phase(128.0, 1000.0, 0.0) == 0.0


def test_deck_visual_energy_clamped():
    assert deck_visual_energy(1.0, 2.0) == 1.0
    assert deck_visual_energy(0.0, 1.0) == 0.0

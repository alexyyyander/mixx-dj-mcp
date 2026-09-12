"""Resolume OSC client aligned with resolume-mcp address conventions.

Resolume listens for control messages on its *incoming* OSC port (default 7000).
See resolume-mcp ``utils/resolume_osc.py`` and osc-mcp ``resolume-expert`` skill.
"""

from __future__ import annotations

import os
from typing import Any

from pythonosc import udp_client

# Resolume composition (match resolume-mcp; tempocontroller alias per osc-mcp fix)
OSC_MASTER_BPM_PRIMARY = "/composition/tempomap/bpm"
OSC_MASTER_BPM_ALT = "/composition/tempocontroller/tempo"


def resolume_host() -> str:
    return os.getenv("RESOLUME_OSC_HOST", "127.0.0.1")


def resolume_port() -> int:
    return int(os.getenv("RESOLUME_OSC_PORT", "7000"))


def layer_opacity_address(layer: int) -> str:
    return f"/composition/layers/{layer}/opacity"


def effect_param_address(layer: int, effect: int, parameter: int) -> str:
    return f"/composition/layers/{layer}/effects/{effect}/params/{parameter}/value"


def clip_connect_address(layer: int, clip: int) -> str:
    return f"/composition/layers/{layer}/clips/{clip}/connect"


class ResolumeOscSender:
    """Fire-and-forget UDP OSC to Resolume."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        h = host or resolume_host()
        p = port if port is not None else resolume_port()
        self._client = udp_client.SimpleUDPClient(h, p)
        self.host = h
        self.port = p

    def send_float(self, address: str, value: float) -> None:
        self._client.send_message(address, float(value))

    def set_master_bpm(self, bpm: float) -> None:
        bpm = max(1.0, min(300.0, float(bpm)))
        self.send_float(OSC_MASTER_BPM_PRIMARY, bpm)
        self.send_float(OSC_MASTER_BPM_ALT, bpm)

    def set_layer_opacity(self, layer: int, opacity: float) -> None:
        self.send_float(layer_opacity_address(layer), max(0.0, min(1.0, opacity)))

    def set_effect_param(self, layer: int, effect: int, param: int, value: float) -> None:
        self.send_float(
            effect_param_address(layer, effect, param),
            max(0.0, min(1.0, value)),
        )

    def trigger_clip(self, layer: int, clip: int) -> None:
        self.send_float(clip_connect_address(layer, clip), 1.0)


def deck_visual_energy(volume: float, pregain: float) -> float:
    return min(1.0, max(0.0, float(volume) * float(pregain) * 1.5))


def deck_beat_phase(bpm: float, track_samples: float, sample_rate: float) -> float:
    if sample_rate <= 0 or bpm <= 0:
        return 0.0
    beats_per_second = bpm / 60.0
    seconds = track_samples / sample_rate
    return (seconds * beats_per_second) % 1.0


def resolume_sync_from_deck_state(
    sender: ResolumeOscSender,
    *,
    bpm: float,
    deck: int,
    playing: float,
    volume: float,
) -> dict[str, Any]:
    sender.set_master_bpm(bpm)
    return {
        "bpm": bpm,
        "deck": deck,
        "playing": bool(playing),
        "volume": volume,
        "osc_host": sender.host,
        "osc_port": sender.port,
    }


def resolume_visuals_from_deck_state(
    sender: ResolumeOscSender,
    *,
    bpm: float,
    track_samples: float,
    sample_rate: float,
    volume: float,
    pregain: float,
    fx_layer: int = 2,
    accent_layer: int = 3,
) -> dict[str, Any]:
    beat_phase = deck_beat_phase(bpm, track_samples, sample_rate)
    energy = deck_visual_energy(volume, pregain)
    beat_flash = 1.0 if beat_phase < 0.05 else max(0.0, 1.0 - (beat_phase * 2))

    sender.set_master_bpm(bpm)
    sender.set_layer_opacity(fx_layer, energy)
    sender.set_effect_param(fx_layer, 1, 1, bpm / 200.0)
    sender.set_effect_param(fx_layer, 1, 2, beat_phase)
    sender.set_effect_param(fx_layer, 1, 3, energy)
    sender.set_layer_opacity(accent_layer, beat_flash)
    sender.set_effect_param(accent_layer, 1, 1, beat_phase)

    return {
        "bpm": bpm,
        "beat_phase": beat_phase,
        "energy": energy,
        "beat_flash": beat_flash,
        "fx_layer": fx_layer,
        "accent_layer": accent_layer,
    }


def resolume_trigger_effect(sender: ResolumeOscSender, effect: str, intensity: float) -> None:
    intensity = max(0.0, min(1.0, intensity))
    if effect == "strobe":
        sender.set_layer_opacity(3, intensity)
        sender.set_effect_param(3, 1, 1, 0.0)
    elif effect == "pulse":
        sender.set_effect_param(2, 1, 1, intensity)
        sender.set_layer_opacity(2, 1.0)
    elif effect == "color_cycle":
        sender.set_effect_param(2, 1, 3, 1.0)
    elif effect == "wave":
        sender.set_effect_param(2, 2, 1, intensity)
    elif effect == "particles":
        sender.set_layer_opacity(4, 1.0)
    else:
        raise ValueError(effect)

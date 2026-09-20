import pytest

from mixx_dj_mcp.ai_dj_runtime import AiDjRuntime, AiDjRuntimeError


def test_transition_rehearsal_remaps_decks_and_keeps_relative_beats():
    runtime = AiDjRuntime("/tmp/mixxx-ai-dj-test")
    plan = {
        "plan_id": "transition-test",
        "target_bpm": 128,
        "duration_beats": 16,
        "operations": [
            {"relative_beat": 0, "kind": "control", "path": "decks/2/play", "value": 1},
            {"relative_beat": 16, "kind": "control", "path": "decks/1/play", "value": 0},
        ],
    }

    rehearsal = runtime.transition_rehearsal(plan, deck_out=3, deck_in=4)

    assert rehearsal["scheduled"] is False
    assert [item["relative_beat"] for item in rehearsal["requests"]] == [0, 16]
    assert rehearsal["requests"][0]["payload"]["path"] == "decks/4/play"
    assert rehearsal["requests"][1]["payload"]["path"] == "decks/3/play"


def test_repository_status_does_not_require_the_bridge():
    runtime = AiDjRuntime("/tmp/mixxx-ai-dj-test", bridge_url="http://127.0.0.1:1")

    status = runtime.repository_status()

    assert status["live_control_enabled"] is False
    assert status["execution_clock"] == "backend-relative-beat-best-effort"


@pytest.mark.parametrize(
    "operation",
    [
        {"relative_beat": -1, "kind": "control", "path": "decks/1/play", "value": 1},
        {"relative_beat": 0, "kind": "control", "path": "../mixer/crossfader", "value": 1},
        {"relative_beat": 0, "kind": "control", "path": "library/delete", "value": 1},
        {"relative_beat": 0, "kind": "control", "path": "mixer/crossfader", "value": 2},
    ],
)
def test_transition_rehearsal_rejects_unsafe_operations(operation):
    runtime = AiDjRuntime("/tmp/mixxx-ai-dj-test")
    with pytest.raises(AiDjRuntimeError):
        runtime.transition_rehearsal(
            {"plan_id": "unsafe", "operations": [operation]},
            deck_out=1,
            deck_in=2,
        )


def test_transition_rehearsal_rejects_out_of_order_beats():
    runtime = AiDjRuntime("/tmp/mixxx-ai-dj-test")
    with pytest.raises(AiDjRuntimeError, match="ordered"):
        runtime.transition_rehearsal(
            {
                "plan_id": "out-of-order",
                "operations": [
                    {"relative_beat": 8, "kind": "control", "path": "mixer/crossfader", "value": 0},
                    {"relative_beat": 4, "kind": "control", "path": "mixer/crossfader", "value": 1},
                ],
            },
            deck_out=1,
            deck_in=2,
        )

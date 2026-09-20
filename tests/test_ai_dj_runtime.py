from mixx_dj_mcp.ai_dj_runtime import AiDjRuntime


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

"""Runtime adapter between mixxx-ai-dj profiles and mixxx-api-bridge.

The AI models live in the separate ``mixxx-ai-dj`` repository.  This module
keeps the web/MCP application lightweight: it discovers analyzed profiles,
builds deterministic tag maps and transition plans through that repository,
and sends explicitly armed commands through the acknowledged HTTP bridge.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


class AiDjRuntimeError(RuntimeError):
    """Raised when the analysis repository or API bridge is unavailable."""


class AiDjRuntime:
    def __init__(
        self,
        root: str | Path,
        *,
        profiles_dir: str | Path | None = None,
        bridge_url: str = "http://127.0.0.1:11120",
        bridge_token: str | None = None,
        allow_live: bool = False,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.profiles_dir = (
            Path(profiles_dir).expanduser().resolve()
            if profiles_dir
            else self.root / "artifacts" / "profiles"
        )
        if not profiles_dir and not self.profiles_dir.exists():
            self.profiles_dir = self.root / "examples" / "analyzed"
        self.bridge_url = bridge_url.rstrip("/")
        self.bridge_token = bridge_token
        self.allow_live = allow_live
        self.jobs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @classmethod
    def from_env(cls) -> "AiDjRuntime":
        default_root = Path(__file__).resolve().parents[3] / "mixxx-ai-dj"
        return cls(
            os.getenv("MIXXX_AI_DJ_ROOT", str(default_root)),
            profiles_dir=os.getenv("MIXXX_AI_DJ_PROFILES_DIR"),
            bridge_url=os.getenv("MIXXX_API_BRIDGE_URL", "http://127.0.0.1:11120"),
            bridge_token=os.getenv("MIXXX_API_TOKEN"),
            allow_live=os.getenv("MIXXX_AI_DJ_ALLOW_LIVE", "false").lower() in {"1", "true", "yes"},
        )

    def _load_ai_modules(self) -> dict[str, Any]:
        source_root = self.root / "src"
        if not source_root.is_dir():
            raise AiDjRuntimeError(
                f"mixxx-ai-dj source not found at {source_root}; set MIXXX_AI_DJ_ROOT"
            )
        source = str(source_root)
        if source not in sys.path:
            sys.path.insert(0, source)
        try:
            from mixxx_ai_dj.bridge import rehearse_plan
            from mixxx_ai_dj.io import track_profile_from_dict
            from mixxx_ai_dj.markers import build_dj_tag_map, rehearse_marker_map
            from mixxx_ai_dj.planner import plan_transition
        except (ImportError, ModuleNotFoundError) as exc:
            raise AiDjRuntimeError(f"cannot import mixxx-ai-dj: {exc}") from exc
        return {
            "build_dj_tag_map": build_dj_tag_map,
            "plan_transition": plan_transition,
            "read_profile": track_profile_from_dict,
            "rehearse_marker_map": rehearse_marker_map,
            "rehearse_plan": rehearse_plan,
        }

    def repository_status(self) -> dict[str, Any]:
        return {
            "available": (self.root / "src" / "mixxx_ai_dj").is_dir(),
            "root": str(self.root),
            "profiles_dir": str(self.profiles_dir),
            "profile_count": len(self.list_profiles()),
            "bridge_url": self.bridge_url,
            "live_control_enabled": self.allow_live,
            "execution_clock": "backend-relative-beat-best-effort",
        }

    def list_profiles(self) -> list[dict[str, Any]]:
        if not self.profiles_dir.is_dir():
            return []
        profiles: list[dict[str, Any]] = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("schema_version") != "1.0" or not data.get("track_id"):
                    continue
                tags = data.get("tags") or {}
                top_tags = [
                    items[0].get("label")
                    for items in tags.values()
                    if isinstance(items, list) and items and isinstance(items[0], dict)
                ]
                profiles.append(
                    {
                        "track_id": data["track_id"],
                        "source_path": data.get("source_path", ""),
                        "duration_seconds": data.get("duration_seconds", 0),
                        "bpm": data.get("bpm"),
                        "key_camelot": data.get("key_camelot"),
                        "vocal_probability": data.get("vocal_probability"),
                        "segments": len(data.get("segments") or []),
                        "beats": len(data.get("beats") or []),
                        "stems": sorted((data.get("stems") or {}).keys()),
                        "top_tags": [tag for tag in top_tags if tag],
                    }
                )
            except (OSError, json.JSONDecodeError, TypeError):
                continue
        return profiles

    def _profile_path(self, track_id: str) -> Path:
        if not track_id or Path(track_id).name != track_id:
            raise AiDjRuntimeError("invalid track_id")
        path = (self.profiles_dir / f"{track_id}.json").resolve()
        if path.parent != self.profiles_dir.resolve() or not path.is_file():
            raise AiDjRuntimeError(f"profile not found: {track_id}")
        return path

    def profile_document(self, track_id: str) -> dict[str, Any]:
        try:
            data = json.loads(self._profile_path(track_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AiDjRuntimeError(f"cannot read profile {track_id}: {exc}") from exc
        if not isinstance(data, dict):
            raise AiDjRuntimeError(f"profile is not a JSON object: {track_id}")
        return data

    def marker_document(self, track_id: str, *, deck: int = 1) -> dict[str, Any]:
        if deck not in range(1, 5):
            raise AiDjRuntimeError("deck must be between 1 and 4")
        self._profile_path(track_id)
        for directory in (self.root / "artifacts" / "dj-tags", self.root / "examples" / "tags"):
            sidecar = directory / f"{track_id}.json"
            if sidecar.is_file():
                try:
                    document = json.loads(sidecar.read_text(encoding="utf-8"))
                    if isinstance(document, dict):
                        return document
                except (OSError, json.JSONDecodeError):
                    pass
        modules = self._load_ai_modules()
        profile = modules["read_profile"](self.profile_document(track_id))
        return modules["build_dj_tag_map"](profile).to_dict()

    def marker_rehearsal(self, track_id: str, *, deck: int = 1) -> dict[str, Any]:
        modules = self._load_ai_modules()
        profile = modules["read_profile"](self.profile_document(track_id))
        marker_map = modules["build_dj_tag_map"](profile)
        return modules["rehearse_marker_map"](marker_map, deck=deck)

    def transition_plan(
        self,
        from_track_id: str,
        to_track_id: str,
        *,
        duration_beats: int = 32,
    ) -> dict[str, Any]:
        modules = self._load_ai_modules()
        first = modules["read_profile"](self.profile_document(from_track_id))
        second = modules["read_profile"](self.profile_document(to_track_id))
        return modules["plan_transition"](
            first,
            second,
            duration_beats=duration_beats,
        ).to_dict()

    @staticmethod
    def _remap_path(path: str, *, deck_out: int, deck_in: int) -> str:
        if path.startswith("decks/1/"):
            return f"decks/{deck_out}/{path.removeprefix('decks/1/')}"
        if path.startswith("decks/2/"):
            return f"decks/{deck_in}/{path.removeprefix('decks/2/')}"
        return path

    def transition_rehearsal(
        self,
        plan: dict[str, Any],
        *,
        deck_out: int = 1,
        deck_in: int = 2,
    ) -> dict[str, Any]:
        if deck_out not in range(1, 5) or deck_in not in range(1, 5) or deck_out == deck_in:
            raise AiDjRuntimeError("deck_out and deck_in must be different decks between 1 and 4")
        requests = []
        for operation in plan.get("operations") or []:
            endpoint = "/api/control" if operation.get("kind") == "control" else "/api/action"
            payload: dict[str, Any] = {
                "path": self._remap_path(
                    str(operation.get("path", "")),
                    deck_out=deck_out,
                    deck_in=deck_in,
                )
            }
            if operation.get("value") is not None:
                payload["value"] = operation["value"]
            if operation.get("action") is not None:
                payload["action"] = operation["action"]
            requests.append(
                {
                    "relative_beat": float(operation.get("relative_beat", 0)),
                    "endpoint": endpoint,
                    "payload": payload,
                    "scheduled": False,
                }
            )
        return {
            "plan_id": plan.get("plan_id"),
            "deck_out": deck_out,
            "deck_in": deck_in,
            "target_bpm": plan.get("target_bpm"),
            "duration_beats": plan.get("duration_beats"),
            "scheduled": False,
            "clock": "relative beat preview; live jobs use a best-effort backend clock",
            "requests": requests,
        }

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.bridge_token:
            headers["Authorization"] = f"Bearer {self.bridge_token}"
        return headers

    async def bridge_health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.bridge_url}/api/health", headers=self._headers())
                response.raise_for_status()
                data = response.json()
            bridge_state = data.get("bridge") if isinstance(data.get("bridge"), dict) else {}
            return {
                "reachable": True,
                "connected": bool(data.get("connected", bridge_state.get("connected"))),
                "status": data,
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {"reachable": False, "connected": False, "error": str(exc)}

    async def _require_live_bridge(self) -> None:
        if not self.allow_live:
            raise AiDjRuntimeError(
                "live control is locked; set MIXXX_AI_DJ_ALLOW_LIVE=1 and restart after reviewing the plan"
            )
        health = await self.bridge_health()
        if not health.get("reachable"):
            raise AiDjRuntimeError(f"mixxx-api-bridge is unreachable: {health.get('error', 'unknown error')}")
        if not health.get("connected"):
            raise AiDjRuntimeError("mixxx-api-bridge is running but its Mixxx mapping is not connected")

    async def _bridge_post(self, endpoint: str, payload: dict[str, Any], *, wait_ms: int) -> dict[str, Any]:
        request = {**payload, "wait_ms": wait_ms}
        async with httpx.AsyncClient(timeout=max(6.0, wait_ms / 1000 + 2.0)) as client:
            response = await client.post(
                f"{self.bridge_url}{endpoint}",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=request,
            )
            response.raise_for_status()
            result = response.json()
        if not result.get("accepted"):
            raise AiDjRuntimeError(f"bridge rejected {payload.get('path')}")
        if result.get("connected") is False:
            raise AiDjRuntimeError("bridge lost its Mixxx mapping connection")
        if result.get("timed_out"):
            raise AiDjRuntimeError(f"no Mixxx ACK for {payload.get('path')}")
        return result

    async def apply_markers(
        self,
        track_id: str,
        *,
        deck: int,
        confirmed: bool,
        wait_ms: int = 1000,
    ) -> dict[str, Any]:
        rehearsal = self.marker_rehearsal(track_id, deck=deck)
        if not confirmed:
            return {
                "success": False,
                "requires_confirmation": True,
                "message": "Pause the deck, review marker positions, then confirm live hotcue writes.",
                "rehearsal": rehearsal,
            }
        await self._require_live_bridge()
        results = []
        for request in rehearsal["requests"]:
            results.append(
                await self._bridge_post(
                    request["endpoint"],
                    request["payload"],
                    wait_ms=wait_ms,
                )
            )
        return {
            "success": True,
            "message": f"Applied {len(rehearsal['requests']) // 2} hotcues to deck {deck}",
            "track_id": track_id,
            "deck": deck,
            "results": results,
        }

    async def start_transition(
        self,
        plan: dict[str, Any],
        *,
        deck_out: int,
        deck_in: int,
        confirmed: bool,
        wait_ms: int = 1000,
    ) -> dict[str, Any]:
        rehearsal = self.transition_rehearsal(plan, deck_out=deck_out, deck_in=deck_in)
        if not confirmed:
            return {
                "success": False,
                "requires_confirmation": True,
                "message": "Review the relative-beat request list before arming live control.",
                "rehearsal": rehearsal,
            }
        await self._require_live_bridge()
        job_id = f"transition-{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "kind": "transition",
            "status": "queued",
            "created_at": time.time(),
            "plan_id": plan.get("plan_id"),
            "track_id": plan.get("to_track_id"),
            "current_beat": 0.0,
            "duration_beats": rehearsal.get("duration_beats", 0),
            "completed_requests": 0,
            "request_count": len(rehearsal["requests"]),
        }
        self.jobs[job_id] = job
        self._tasks[job_id] = asyncio.create_task(
            self._run_transition_job(job_id, rehearsal, wait_ms=wait_ms)
        )
        return {"success": True, "message": "AI DJ transition armed", "job": dict(job)}

    async def _run_transition_job(
        self,
        job_id: str,
        rehearsal: dict[str, Any],
        *,
        wait_ms: int,
    ) -> None:
        job = self.jobs[job_id]
        job["status"] = "running"
        job["started_at"] = time.time()
        start = time.monotonic()
        seconds_per_beat = 60.0 / max(float(rehearsal.get("target_bpm") or 120), 1.0)
        try:
            for request in rehearsal["requests"]:
                beat = float(request.get("relative_beat", 0))
                deadline = start + beat * seconds_per_beat
                await asyncio.sleep(max(0.0, deadline - time.monotonic()))
                await self._bridge_post(request["endpoint"], request["payload"], wait_ms=wait_ms)
                job["current_beat"] = beat
                job["completed_requests"] += 1
            job["status"] = "complete"
            job["completed_at"] = time.time()
        except asyncio.CancelledError:
            job["status"] = "cancelled"
            job["completed_at"] = time.time()
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
            job["completed_at"] = time.time()

    async def start_analysis(self, audio_path: str, *, device: str = "cpu") -> dict[str, Any]:
        if device not in {"cpu", "cuda", "mps"}:
            raise AiDjRuntimeError("device must be cpu, cuda, or mps")
        audio = Path(audio_path).expanduser().resolve()
        if not audio.is_file():
            raise AiDjRuntimeError(f"audio file not found: {audio}")
        if not (self.root / "src" / "mixxx_ai_dj").is_dir():
            raise AiDjRuntimeError(f"mixxx-ai-dj repository not found: {self.root}")
        job_id = f"analysis-{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "kind": "analysis",
            "status": "queued",
            "created_at": time.time(),
            "audio_path": str(audio),
            "device": device,
        }
        self.jobs[job_id] = job
        self._tasks[job_id] = asyncio.create_task(self._run_analysis_job(job_id, audio, device=device))
        return {"success": True, "message": "Full AI analysis queued", "job": dict(job)}

    async def _run_analysis_job(self, job_id: str, audio: Path, *, device: str) -> None:
        job = self.jobs[job_id]
        job["status"] = "running"
        job["started_at"] = time.time()
        executable = self.root / ".venv" / "bin" / "mixxx-ai-dj"
        if executable.is_file():
            command = [
                str(executable),
                "pipeline",
                str(audio),
                "--work-dir",
                str(self.root / "artifacts"),
                "--device",
                device,
                "--overwrite",
            ]
        else:
            command = [
                sys.executable,
                "-m",
                "mixxx_ai_dj",
                "pipeline",
                str(audio),
                "--work-dir",
                str(self.root / "artifacts"),
                "--device",
                device,
                "--overwrite",
            ]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(self.root / "src"), environment.get("PYTHONPATH", "")])
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.root,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            job["stdout"] = stdout.decode("utf-8", errors="replace")[-8000:]
            job["stderr"] = stderr.decode("utf-8", errors="replace")[-8000:]
            job["return_code"] = process.returncode
            job["status"] = "complete" if process.returncode == 0 else "failed"
            if process.returncode:
                job["error"] = job["stderr"].strip() or "analysis command failed"
            output_paths = [
                line.strip()
                for line in job["stdout"].splitlines()
                if line.strip().endswith(".json")
            ]
            if output_paths:
                job["profile_path"] = output_paths[-1]
                job["track_id"] = Path(output_paths[-1]).stem
            job["completed_at"] = time.time()
        except asyncio.CancelledError:
            job["status"] = "cancelled"
            job["completed_at"] = time.time()
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
            job["completed_at"] = time.time()

    def job(self, job_id: str) -> dict[str, Any]:
        if job_id not in self.jobs:
            raise AiDjRuntimeError(f"job not found: {job_id}")
        return dict(self.jobs[job_id])

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        if job_id not in self.jobs:
            raise AiDjRuntimeError(f"job not found: {job_id}")
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            self.jobs[job_id]["status"] = "cancelling"
        return {"success": True, "job": dict(self.jobs[job_id])}

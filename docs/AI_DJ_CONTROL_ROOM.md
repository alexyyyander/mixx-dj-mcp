# AI DJ Control Room

AI DJ Control Room is the visual orchestration layer for the separate
[`mixxx-ai-dj`](https://github.com/alexyyyander/mixxx-ai-dj) analysis pipeline and
[`mixxx-api-bridge`](https://github.com/alexyyyander/mixxx-api-bridge). Open the
webapp at `/#/ai-dj` to inspect analyzed tracks, DJ timeline markers, hotcue
suggestions, and an explainable transition plan.

## What it does

1. Lists `TrackProfile` JSON files from `MIXXX_AI_DJ_ROOT/artifacts/profiles`.
2. Shows BPM, Camelot key, vocal probability, semantic tags, section markers,
   phrase grid and up to eight hotcue suggestions.
3. Runs a background `mixxx-ai-dj pipeline` job for a new local audio file.
4. Generates a transition plan and an unscheduled, reviewable API Bridge request
   list.
5. Can apply hotcue writes or start a beat-paced transition job only after a
   human confirmation and the live guard is explicitly enabled.

## Start locally

```bash
# terminal 1 — acknowledged Mixxx control bridge
cd mixxx-api-bridge
uv sync
uv run mixxx-api-bridge serve

# terminal 2 — MCP + REST backend
cd mixx-dj-mcp
uv sync
MIXXX_AI_DJ_ROOT=../mixxx-ai-dj \
MIXXX_API_BRIDGE_URL=http://127.0.0.1:11120 \
uv run uvicorn mixx_dj_mcp.server:app --port 11116

# terminal 3 — visual control room
cd mixx-dj-mcp/web_sota
bun install
bun run dev
```

Then open `http://127.0.0.1:11117/#/ai-dj`.

The live guard is deliberately off by default. After checking the request list,
Mixxx mapping and deck state, enable it for a session with
`MIXXX_AI_DJ_ALLOW_LIVE=1` and restart the backend. The page still requires the
checkbox confirmation before sending commands.

## REST surface

| Endpoint | Purpose |
| --- | --- |
| `GET /api/ai-dj/status` | Repository, bridge and live-guard status |
| `GET /api/ai-dj/profiles` | Profile summaries for the track selectors |
| `GET /api/ai-dj/profiles/{id}/markers` | Marker/hotcue map for the timeline |
| `POST /api/ai-dj/analyze` | Queue a full AI analysis job (`audio_path`, `device`) |
| `POST /api/ai-dj/plan` | Build a plan plus bridge rehearsal requests |
| `POST /api/ai-dj/rehearse` | Explicit dry-run plan endpoint |
| `POST /api/ai-dj/execute` | Confirm and queue a live transition job |
| `POST /api/ai-dj/markers/apply` | Confirm and write selected hotcues |
| `GET /api/ai-dj/jobs/{id}` | Poll analysis or transition progress |

The bridge request list retains `relative_beat` for auditing. The current HTTP
bridge does not provide sample-accurate scheduling, so the live worker uses a
backend monotonic clock and waits for each relative beat. For club-safe,
sample-accurate automation, the next step is a Mixxx mapping/scheduler that
consumes this same plan inside Mixxx.

## English App – Backend Integration Notes

The repository hosts two projects:

- `src/english_app_agent`: LangGraph-based backend that orchestrates mnemonic/image/TTS generation.
- `src/web`: Next.js 14 chat UI that proxies requests to the Python agent.

This document focuses on the backend and assumes you manage Python dependencies with [uv](https://github.com/astral-sh/uv), which provides an ultra-fast drop-in replacement for `pip`/`venv`.

### Prerequisites

- Python 3.10+ (matching the agent code requirements)
- [`uv`](https://github.com/astral-sh/uv#installation) installed globally
- Optional: Node.js 18+ if you plan to run the frontend alongside the backend

### Setup With uv

1. **Install dependencies**
   ```bash
   cd E:/code/English_app
   uv pip install -r requirements.txt
   ```

   The `requirements.txt` file mirrors everything the agent imports (`langgraph`, `fastapi`, `dashscope`, etc.). uv creates and reuses an isolated environment automatically (stored under `.venv` unless configured otherwise).

2. **Set environment variables**
   - Copy `.env.example` (if provided) or edit `.env` directly.
   - Typical keys:
     - `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`, `GOOGLE_API_KEY` for LLM/image/TTS access
     - `GET_API_KEYS_FROM_CONFIG=true` if you prefer passing keys via `RunnableConfig.configurable.apiKeys`

3. **Run database- or cache-related services** (if any). Currently the LangGraph flow relies on `InMemorySaver`, so no external store is needed.

### Running the Backend

The FastAPI entry point lives at `src/english_app_agent/server.py` and exposes `/health` and `/chat`.

```bash
uv run uvicorn english_app_agent.server:app --app-dir src --reload --port 8000
```

- `--app-dir src` lets uvicorn find the `english_app_agent` package without altering `PYTHONPATH`.
- `--reload` is optional but useful while iterating on prompts or graph logic.
- Set `AGENT_API_BASE_URL=http://127.0.0.1:8000` in the frontend env so `/api/chat` proxies requests to this service.


### Skills Integration

The mnemonic agent injects skills at runtime using `src/english_app_agent/skills_provider.py`:

- Skills live under `skills/<skill-name>/SKILL.md` with optional `references/` files.
- `SkillManager` discovers skills, selects with a keyword/BM25 selector, and injects the selected skill body into the mnemonic prompt.
- References like `references/phoneme-mapping.md` are appended when present.
- Skills refresh on a 60s TTL, so you can update files without restarting the server.

### Storage & Persistence

Every successful `/chat` response flows through a tiered storage manager:

1. **Local cache (default on)** – Results are serialized to `~/.english_app_agent/cache`. The cache trims itself when file count exceeds `max_entries` (default 200). Tune via `EnglishAppConfig.storage.local_cache`.
2. **Remote database (optional)** – Set `storage.remote_database.enable=true` and provide a SQLAlchemy URL (MySQL or PostgreSQL). Structured payloads are inserted into the `chat_responses` table automatically.
3. **Media mirroring (optional)** – Enabling `storage.media` with `provider="aliyun_oss"` and valid OSS credentials instructs the backend to copy image/audio URLs into your bucket. The returned `final_output.media.*.url` will reflect the mirrored location.

Feature flags can be toggled via environment variables or by supplying a JSON blob under the `storage` key inside `RunnableConfig.configurable`.

#### Configuring `storage_config.py`

`src/english_app_agent/storage_config.py` reads settings from two sources (merged in this order):

1. `RunnableConfig.configurable.storage` (useful for per-request overrides).
2. Environment variables (best for `.env`/deployment defaults).

Key env vars you can drop into `.env`:

```ini
# Local cache (defaults shown)
LOCAL_CACHE_ENABLE=true
LOCAL_CACHE_DIR=~/.english_app_agent/cache
LOCAL_CACHE_MAX_ENTRIES=200

# Remote DB
REMOTE_DB_ENABLE=false
REMOTE_DB_URL=postgresql+psycopg2://user:pass@host/dbname

# Media mirroring
MEDIA_ENABLE=true
MEDIA_PROVIDER=local_fs        # or aliyun_oss / none
MEDIA_LOCAL_DIRECTORY=~/.english_app_agent/media
# Aliyun OSS-only fields:
MEDIA_BUCKET=your-bucket
MEDIA_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
MEDIA_ACCESS_KEY_ID=...
MEDIA_ACCESS_KEY_SECRET=...
MEDIA_PREFIX=chat_media/

# Cache archive (optional OSS backup for records)
ARCHIVE_ENABLE=false
ARCHIVE_BUCKET=...
ARCHIVE_ENDPOINT=...
ARCHIVE_ACCESS_KEY_ID=...
ARCHIVE_ACCESS_KEY_SECRET=...
ARCHIVE_PREFIX=chat_cache/
```

When editing `storage_config.py`, keep the Pydantic models aligned with these env names—each field uses a helper (`_env_bool`, `_env_int`, or `os.getenv`). On the frontend/CLI side, pass overrides like:

```python
config = {
    "configurable": {
        "thread_id": "abc123",
        "storage": {
            "media": {"provider": "local_fs", "local_directory": "/tmp/english-app/media"}
        }
    }
}
```

This lets you tailor caching/media policies per request without touching global env vars.

### Invoking the Agent Manually

```bash
uv run python - <<'PY'
import asyncio
from english_app_agent.agent import app_agent

async def main():
    state = await app_agent.ainvoke(
        {"messages": [{"type": "human", "content": "Help me remember ambulance"}]},
        config={"configurable": {"thread_id": "debug-cli"}}
    )
    print(state["reply_text"])

asyncio.run(main())
PY
```

### Testing

`test/test_main_agent_logic.py` currently serves as a placeholder. When tests are added, run them with:

```bash
uv run python -m pytest
```

### Frontend Hook-Up

1. `cd src/web && npm install`
2. `AGENT_API_BASE_URL=http://127.0.0.1:8000 npm run dev`
3. The Next.js API route (`/api/chat`) forwards chat payloads to the FastAPI backend, so keep both servers running for the full experience.

### Troubleshooting

- **CORS errors**: `server.py` enables permissive CORS, but you can narrow `allow_origins` once deployment domains are known.
- **API errors**: `/api/chat` surfaces backend exceptions via JSON `{ error: "..." }`. Check the FastAPI logs for stack traces.
- **Missing keys**: The agent reads provider keys from env vars unless `GET_API_KEYS_FROM_CONFIG=true`, in which case pass them via `configurable.apiKeys`.

### Dashboard API

When `backend.data_dashboard` is installed, the main FastAPI app automatically mounts it under `/dashboard`. Configure the repository connection via:

```ini
DATA_DASHBOARD_DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname
```

If the env var is missing you can still POST inline telemetry by hitting `/dashboard/dashboard` with `events` and `memberships` arrays (see `src/backend/data_dashboard/README.md` for a template). Run the unified server as usual:

```bash
uv run uvicorn english_app_agent.server:app --app-dir src --reload --port 8000
```

The mounted sub-application also exposes `/dashboard/health`.

With uv managing dependencies and FastAPI hosting both the LangGraph flow and dashboard routes, the backend remains lightweight and easy to iterate alongside the Next.js frontend.

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

### Storage & Persistence

Every successful `/chat` response flows through a tiered storage manager:

1. **Local cache (default on)** – Results are serialized to `~/.english_app_agent/cache`. The cache trims itself when file count exceeds `max_entries` (default 200). Tune via `EnglishAppConfig.storage.local_cache`.
2. **Remote database (optional)** – Set `storage.remote_database.enable=true` and provide a SQLAlchemy URL (MySQL or PostgreSQL). Structured payloads are inserted into the `chat_responses` table automatically.
3. **Media mirroring (optional)** – Enabling `storage.media` with `provider="aliyun_oss"` and valid OSS credentials instructs the backend to copy image/audio URLs into your bucket. The returned `final_output.media.*.url` will reflect the mirrored location.

Feature flags can be toggled via environment variables or by supplying a JSON blob under the `storage` key inside `RunnableConfig.configurable`.

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

With uv managing dependencies and FastAPI hosting the compiled LangGraph, the backend remains lightweight and easy to iterate alongside the Next.js frontend.***

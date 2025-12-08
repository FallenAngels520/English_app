# Repository Guidelines

## Project Structure & Module Organization
- `src/english_app_agent/agent.py` hosts the LangGraph flow (main agent, mnemonic/image/TTS nodes, final result).
- `src/english_app_agent/state.py` defines the pydantic models that shape decisions, styles, and outputs.
- `src/english_app_agent/configuration.py` loads defaults, feature flags, safety limits, and retry settings.
- `src/english_app_agent/prompt.py` keeps prompt templates; keep placeholders intact when editing.
- `src/english_app_agent/utils.py` handles API key lookup and stubbed tool calls; extend these instead of inlining utilities.
- `test/test_main_agent_logic.py` is a placeholder for pytest coverage; add scenarios here as tests grow.
- `.env` holds local secrets (API keys for LLM/image/TTS); never commit real values.

## Setup & Environment
- Use Python 3.10+ with a virtual env: `python -m venv .venv` then `.venv\Scripts\activate`.
- Dependencies are not pinned; install the current set manually: `python -m pip install langchain langgraph pydantic`.
- If you add packages, record them in a new `requirements.txt` and keep versions consistent across teammates.
- Feature toggles live in `EnglishAppConfig.features` (image/TTS/premium voice switches); set overrides via env vars or the `configurable` block in `RunnableConfig`.

## Build, Test, and Development Commands
- Run tests (async-friendly): `python -m pytest`.
- Lint/formatting is unset; prefer `ruff` and `black` locally if you need consistency, but do not block others without documenting the toolchain.
- To experiment with the graph, import `app_agent` from `src/english_app_agent/agent.py` and call it with a `RunnableConfig`; keep prompts and state small to limit token use.

## Coding Style & Naming Conventions
- Follow 4-space indentation, type hints, and pydantic `BaseModel` subclasses for structured payloads.
- Modules and functions use `snake_case`; classes use `PascalCase`; constants/config defaults stay uppercase.
- Keep prompts readable: f-string style placeholders like `{word}` should remain descriptive and lowercase.
- Route logic should stay in async graph nodes; avoid side effects outside `Command(update=..., goto=...)`.

## Testing Guidelines
- Name tests by behavior (`test_main_agent_logic_routes_new_word`, etc.) and place them under `test/`.
- Mark coroutine tests with `@pytest.mark.asyncio`; provide minimal `AgentState` fixtures to exercise branches (image disabled, premium voice off, out-of-scope intent).
- Assert both state updates and routing (`goto` targets) to prevent silent regressions in the graph.

## Commit & Pull Request Guidelines
- Write imperative commit subjects (`Add mnemonic style fallback`, `Fix TTS downgrade logic`); include issue/feature IDs when available.
- PRs should explain intent, main changes, and test evidence (`pytest` output or reasoning if not run); mention updated configs or env vars.
- Avoid logging sensitive values; rely on `get_api_key_for_model` and feature flags for anything hitting external services.

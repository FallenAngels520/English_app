"""FastAPI server that exposes the English app LangGraph agent."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from .agent import app_agent
from .configuration import EnglishAppConfig
from .state import WordMemoryResult
from .storage import StorageManager
from .storage_config import load_storage_config

try:  # Optional - the dashboard package may not be present in lean deployments.
    from backend.data_dashboard.server import app as dashboard_app
except Exception:  # pragma: no cover - best-effort import
    dashboard_app = None

app = FastAPI(title="English App Agent API", version="0.1.0")
storage_manager = StorageManager()

# Allow cross-origin calls while the project is still iterating.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


def _mount_local_media_directory(target_app: FastAPI) -> None:
    """Expose cached media files when local_fs storage is enabled."""
    storage_config = load_storage_config(None)
    media_cfg = storage_config.media
    if not (media_cfg.enable and media_cfg.provider == "local_fs"):
        return

    media_root = Path(media_cfg.local_directory).expanduser()
    media_root.mkdir(parents=True, exist_ok=True)

    already_mounted = any(
        getattr(route, "path", None) == "/media" for route in target_app.routes
    )
    if not already_mounted:
        target_app.mount("/media", StaticFiles(directory=str(media_root)), name="media")


_mount_local_media_directory(app)

if dashboard_app is not None:
    app.mount("/dashboard", dashboard_app)


class MessagePayload(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Conversation id, mapped to LangGraph thread_id")
    messages: List[MessagePayload] = Field(..., min_length=1)
    configurable: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional overrides forwarded to RunnableConfig.configurable"
    )


class ChatResponse(BaseModel):
    reply_text: str
    final_output: Optional[WordMemoryResult] = None


class CachedResponseRecord(BaseModel):
    session_id: str
    record_id: Optional[str] = None
    cached_at: Optional[str] = None
    request: Dict[str, Any]
    response: ChatResponse


def _convert_messages(messages: List[MessagePayload]):
    converted = []
    for message in messages:
        if message.role == "user":
            converted.append(HumanMessage(content=message.content))
        elif message.role == "assistant":
            converted.append(AIMessage(content=message.content))
        else:
            converted.append(SystemMessage(content=message.content))
    return converted


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    langchain_messages = _convert_messages(request.messages)

    config_payload: RunnableConfig = {
        "configurable": {
            "thread_id": request.session_id,
            **request.configurable,
        }
    }
    config_model = EnglishAppConfig.from_runnable_config(config_payload)
    storage_config = load_storage_config(config_payload)

    try:
        state = await app_agent.ainvoke({"messages": langchain_messages}, config=config_payload)
    except Exception as exc:  # pragma: no cover - bubble up to client
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    reply_text = state.get("reply_text") or ""
    final_output = state.get("final_output")

    if isinstance(final_output, dict):
        final_output = WordMemoryResult(**final_output)

    if final_output:
        final_output = await storage_manager.mirror_media_if_needed(
            final_output,
            storage_config.media,
            session_id=request.session_id,
        )

    response_payload = ChatResponse(reply_text=reply_text, final_output=final_output)

    await storage_manager.persist_response(
        session_id=request.session_id,
        request_payload=request,
        response_payload=response_payload,
        storage_config=storage_config,
    )

    return response_payload


@app.get("/storage/{session_id}", response_model=List[CachedResponseRecord])
async def load_cached_session(
    session_id: str,
    limit: int = Query(5, ge=1, le=50),
) -> List[CachedResponseRecord]:
    storage_config = load_storage_config(None)
    if session_id.lower() == "all":
        session_ids = storage_manager.list_session_ids(storage_config)
        if not session_ids:
            raise HTTPException(status_code=404, detail="No cached sessions available.")
        aggregate: List[Dict[str, Any]] = []
        for sid in session_ids:
            aggregate.extend(await storage_manager.load_cached_records(sid, storage_config, limit=limit))
        normalized = _normalize_records(aggregate)
        if not normalized:
            raise HTTPException(status_code=404, detail="No cached records found.")
        return normalized

    records = await storage_manager.load_cached_records(session_id, storage_config, limit=limit)
    normalized = _normalize_records(records)
    if not normalized:
        raise HTTPException(status_code=404, detail="No cached records found for this session.")
    return normalized


@app.get("/storage/{session_id}/records/{record_id}", response_model=CachedResponseRecord)
async def load_record_detail(session_id: str, record_id: str) -> CachedResponseRecord:
    storage_config = load_storage_config(None)
    record = await storage_manager.load_record_by_id(session_id, record_id, storage_config)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    normalized = _normalize_records([record])
    if not normalized:
        raise HTTPException(status_code=404, detail="Record not found.")
    return normalized[0]


def _normalize_records(records: List[Dict[str, Any]]) -> List[CachedResponseRecord]:
    normalized: List[CachedResponseRecord] = []
    for record in records:
        response_payload = _ensure_dict(record.get("response"))
        try:
            response_model = ChatResponse(**response_payload)
        except Exception:
            continue
        normalized.append(
            CachedResponseRecord(
                session_id=record.get("session_id", ""),
                record_id=record.get("record_id"),
                cached_at=record.get("cached_at"),
                request=_ensure_dict(record.get("request")),
                response=response_model,
            )
        )
    return normalized


def _ensure_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}

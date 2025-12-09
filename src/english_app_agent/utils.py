from langchain_core.runnables import RunnableConfig
import os
import io
import base64

from google import genai
from google.genai import types
from PIL import Image

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal, AsyncIterator, Union

import dashscope
from dashscope import ImageSynthesis
from http import HTTPStatus

_gemini_client: Optional[genai.Client] = None

def _get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        if api_key is None:
            api_key = os.getenv("GOOGLE_API_KEY")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def get_api_key_for_model(model_name: str, config: RunnableConfig):
    """Get API key for a specific model from environment or config."""
    should_get_from_config = os.getenv("GET_API_KEYS_FROM_CONFIG", "false")
    model_name = model_name.lower()
    if should_get_from_config.lower() == "true":
        api_keys = config.get("configurable", {}).get("apiKeys", {})
        if not api_keys:
            return None
        if model_name.startswith("openai:"):
            return api_keys.get("OPENAI_API_KEY")
        elif model_name.startswith("anthropic:"):
            return api_keys.get("ANTHROPIC_API_KEY")
        elif model_name.startswith("google"):
            return api_keys.get("GOOGLE_API_KEY")
        return None
    else:
        if model_name.startswith("openai:"): 
            return os.getenv("OPENAI_API_KEY")
        elif model_name.startswith("qwen:"):
            return os.getenv("DASHSCOPE_API_KEY")
        elif model_name.startswith("deepseek:"):
            return os.getenv("DEEPSEEK_API_KEY")
        return None

FLASHCARD_DEFAULT_SIZE = "1328*1328"

@dataclass(frozen=True)
class DashScopeImageOptions:
    model: str = "qwen-image-plus "  # 推荐 qwen-image-plus 
    size: str = FLASHCARD_DEFAULT_SIZE         # 默认 1:1 
    prompt_extend: bool = True       # prompt 智能改写 
    watermark: bool = False
    negative_prompt: str = ""
    # 地域：北京/新加坡 base_url 不同 
    base_http_api_url: str = "https://dashscope.aliyuncs.com/api/v1"

def _map_style_to_size(style: Dict[str, Any]) -> str:
    """
    你现在 style 里不一定有 size/aspect_ratio，这里给一个“温和映射”：
    - 支持 style["aspect_ratio"] 取值：'1:1','16:9','4:3','3:4','9:16'
    - 或者直接 style["size"]='1328*1328' 这种
    """
    if not style:
        return "1328*1328"

    if isinstance(style.get("size"), str) and "*" in style["size"]:
        return style["size"]

    ar = style.get("aspect_ratio")
    if ar == "16:9":
        return "1664*928"
    if ar == "4:3":
        return "1472*1140"
    if ar == "3:4":
        return "1140*1472"
    if ar == "9:16":
        return "928*1664"
    return FLASHCARD_DEFAULT_SIZE

def _build_prompt(image_prompt: str, style: Dict[str, Any]) -> str:
    """
    你上游 LLM 已经产出 image_prompt，这里只做轻量风格补丁（可按需删减）。
    """
    tags = []
    if style:
        if style.get("style"):
            tags.append(str(style["style"]))
        if style.get("mood"):
            tags.append(str(style["mood"]))
        extra = style.get("extra_tags") or []
        if isinstance(extra, (list, tuple)):
            tags.extend([str(x) for x in extra if x])

    if tags:
        return f"{image_prompt}\n\nStyle tags: {', '.join(tags)}"
    return image_prompt

def _call_sync(
    prompt: str,
    api_key: str,
    opt: DashScopeImageOptions,
) -> str:
    """
    阻塞：SDK 同步等待任务完成后返回，成功则 results[0].url 是图像 URL（24 小时有效）。 
    """
    dashscope.base_http_api_url = opt.base_http_api_url
    rsp = ImageSynthesis.call(
        api_key=api_key,
        model=opt.model,
        prompt=prompt,
        n=1,
        size=opt.size,
        prompt_extend=opt.prompt_extend,
        watermark=opt.watermark,
        negative_prompt=opt.negative_prompt,
    )

    if rsp.status_code != HTTPStatus.OK:
        raise RuntimeError(f"DashScope ImageSynthesis.call failed: status={rsp.status_code}, code={rsp.code}, message={rsp.message}")

    #再判断 output/results 结构
    output = getattr(rsp, "output", None)
    if not output:
        raise RuntimeError(f"DashScope image response missing output. raw={rsp}")

    results = getattr(output, "results", None)
    if not results:
        # results 为 None 或 [] 都算空
        raise RuntimeError(
            f"DashScope image response has no results. "
            f"task_status={getattr(output, 'task_status', None)} "
            f"usage={getattr(rsp, 'usage', None)} "
            f"raw={rsp}"
        )

    first = results[0]
    url = getattr(first, "url", None)
    if not url:
        raise RuntimeError(f"DashScope image result missing url. first={first} raw={rsp}")

    return url

def _create_task(
    prompt: str,
    api_key: str,
    opt: DashScopeImageOptions,
):
    dashscope.base_http_api_url = opt.base_http_api_url
    rsp = ImageSynthesis.async_call(
        api_key=api_key,
        model=opt.model,
        prompt=prompt,
        n=1,
        size=opt.size,
        prompt_extend=opt.prompt_extend,
        watermark=opt.watermark,
        negative_prompt=opt.negative_prompt,
    )

    if rsp.status_code != HTTPStatus.OK:
        raise RuntimeError(f"DashScope ImageSynthesis.async_call failed: status={rsp.status_code}, code={rsp.code}, message={rsp.message}")

    return rsp  # 里面带 task_id

async def _poll_task(task_rsp, timeout_s: int = 60, interval_s: float = 2.0) -> str:
    """
    轮询 fetch，直到 SUCCEEDED/FAILED 或超时。
    文档示例是循环 fetch 并 sleep，最多轮询 1 分钟。 
    """
    start = asyncio.get_event_loop().time()
    while True:
        if asyncio.get_event_loop().time() - start > timeout_s:
            raise TimeoutError(f"DashScope image task polling timeout after {timeout_s}s")

        # fetch 是阻塞调用，也丢到线程池更安全
        status_rsp = await asyncio.to_thread(ImageSynthesis.fetch, task_rsp)

        if status_rsp.status_code != HTTPStatus.OK:
            raise RuntimeError(f"DashScope ImageSynthesis.fetch failed: status={status_rsp.status_code}, code={status_rsp.code}, message={status_rsp.message}")

        st = status_rsp.output.task_status
        if st == "SUCCEEDED":
            return status_rsp.output.results[0].url
        if st in ("FAILED", "CANCELED"):
            raise RuntimeError(f"DashScope image task failed: task_status={st}")

        await asyncio.sleep(interval_s)

async def generate_image_tool(
    image_prompt: str,
    negative_prompt: str,
    style: Dict[str, Any],
    *,
    api_key: Optional[str] = None,
    mode: Literal["sync_wrapped", "async_task"] = "sync_wrapped",
    model: str = "qwen-image-plus",
    base_http_api_url: str = "https://dashscope.aliyuncs.com/api/v1",
    timeout_s: int = 60,
) -> str:
    """
    LangGraph 友好的 async tool：
    - sync_wrapped: 用 asyncio.to_thread 包住 ImageSynthesis.call（推荐）
    - async_task: 用 async_call 创建任务 + 轮询 fetch

    返回：图像 URL（注意 URL 24 小时有效，请及时下载/保存）。 
    """
    real_key = api_key or os.getenv("DASHSCOPE_API_KEY")
    if not real_key:
        raise RuntimeError("Missing DASHSCOPE_API_KEY env or api_key param")

    opt = DashScopeImageOptions(
        model=model,
        size=_map_style_to_size(style),
        prompt_extend=bool(style.get("prompt_extend", True)),
        watermark=bool(style.get("watermark", False)),
        negative_prompt=negative_prompt,
        base_http_api_url=base_http_api_url,
    )

    prompt = _build_prompt(image_prompt, style)

    if mode == "sync_wrapped":
        # 不阻塞 event loop
        return await asyncio.to_thread(_call_sync, prompt, real_key, opt)

    # 真异步任务（两步）
    task_rsp = await asyncio.to_thread(_create_task, prompt, real_key, opt)
    return await _poll_task(task_rsp, timeout_s=timeout_s, interval_s=2.0)


@dataclass(frozen=True)
class TTSOptions:
    model: str = "qwen3-tts-flash"          # 仅支持 qwen-tts / qwen3-tts 系列 
    voice: str = "Cherry"
    language_type: str = "Chinese"            # Auto / Chinese / English / ... 
    # 北京地域；新加坡替换为 https://dashscope-intl.aliyuncs.com/api/v1 
    base_http_api_url: str = "https://dashscope.aliyuncs.com/api/v1"
    stream: bool = False                   # False: 返回音频URL；True: 流式返回base64片段 


def _parse_audio_url(resp) -> str:
    """
    非流式：从 response.output.audio.url 提取音频URL（24h有效）。
    """
    output = getattr(resp, "output", None) or resp.get("output")
    if not output:
        raise RuntimeError(f"TTS response missing output. raw={resp}")

    audio = getattr(output, "audio", None) if not isinstance(output, dict) else output.get("audio")
    if not audio:
        raise RuntimeError(f"TTS response missing output.audio. raw={resp}")

    url = getattr(audio, "url", None) if not isinstance(audio, dict) else audio.get("url")
    if not url:
        # 失败时常见：output 里会有 finish_reason / message 等，但 audio.url 为空
        raise RuntimeError(f"TTS response audio.url empty. raw={resp}")

    return url


def _call_tts_sync(text: str, api_key: str, opt: TTSOptions):
    """
    同步阻塞调用：dashscope.MultiModalConversation.call
    """
    dashscope.base_http_api_url = opt.base_http_api_url

    # MultiModalConversation 在 dashscope 顶层挂载
    resp = dashscope.MultiModalConversation.call(
        model=opt.model,
        api_key=api_key,
        text=text,
        voice=opt.voice,
        language_type=opt.language_type,
        stream=opt.stream,   # True时会返回一个可迭代流
    )
    return resp


async def tts_generation_tool(
    text: str,
    *,
    api_key: Optional[str] = None,
    model: str = "qwen3-tts-flash",
    voice: str = "Cherry",
    language_type: str = "Chinese",
    base_url: str = "https://dashscope.aliyuncs.com/api/v1",
    stream: bool = False,
) -> Union[str, AsyncIterator[bytes]]:
    """
    语音合成工具：
    - stream=False: 返回音频URL（有效期24小时）
    - stream=True: 返回一个 async iterator，产出音频 bytes（把 base64 解码后的片段吐出来）

    注意：
    - DashScope SDK 是同步阻塞实现，这里用 asyncio.to_thread 包装。
    - 仅支持 qwen-tts / qwen3-tts 系列模型。
    """
    key = api_key or os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("Missing DASHSCOPE_API_KEY env or api_key param")

    opt = TTSOptions(
        model=model,
        voice=voice,
        language_type=language_type,
        base_http_api_url=base_url,
        stream=stream,
    )

    # 1) 非流式：拿到完整 response，解析 output.audio.url
    if not stream:
        resp = await asyncio.to_thread(_call_tts_sync, text, key, opt)
        if resp.status_code != HTTPStatus.OK:
            raise RuntimeError(
                f"TTS call failed: status={resp.status_code}, code={getattr(resp,'code',None)}, message={getattr(resp,'message',None)}"
            )
        return _parse_audio_url(resp)

    # 2) 流式：SDK返回一个 iterator，每个chunk里 audio.data 是 base64 音频片段 
    async def _aiter() -> AsyncIterator[bytes]:
        import base64

        # resp_stream 是同步 iterator，需要在线程里逐个 next
        resp_stream = await asyncio.to_thread(_call_tts_sync, text, key, opt)

        it = iter(resp_stream)
        while True:
            try:
                chunk = await asyncio.to_thread(next, it)
            except StopIteration:
                return

            if chunk.status_code != HTTPStatus.OK:
                raise RuntimeError(
                    f"TTS stream chunk failed: status={chunk.status_code}, code={getattr(chunk,'code',None)}, message={getattr(chunk,'message',None)}"
                )

            output = getattr(chunk, "output", None) or chunk.get("output")
            audio = getattr(output, "audio", None) if not isinstance(output, dict) else output.get("audio")
            data_b64 = getattr(audio, "data", None) if not isinstance(audio, dict) else audio.get("data")

            if data_b64:
                yield base64.b64decode(data_b64)

    return _aiter()


def to_dict_or_self(x):
    if x is None:
        return None
    if hasattr(x, "model_dump"):
        return x.model_dump()
    return x
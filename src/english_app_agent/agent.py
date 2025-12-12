from langchain.chat_models import init_chat_model
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command, Send
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import (
    HumanMessage,
)

from .state import (
    Decision,
    AgentState,
    WordMemoryResult,
    ImageStyle,
    MnemonicStyle,
    VoiceStyle,
    Phonetic,
    Homophone,
    Meaning,
    WordBlock,
    ImageMedia,
    AudioMedia,
    MediaBlock,
    StylesBlock,
    StatusBlock,
    ImageGenOutput,
    TTSGenOutput,
    FinalReplyOutput,
    AgentInputState
    )
from .utils import (
    get_api_key_for_model,
    generate_image_tool,
    tts_generation_tool,
    to_dict_or_self
)
from .configuration import (
    EnglishAppConfig
    )

from .prompt import(
    main_agent_prompt,
    mnemonic_agent_prompt,
    image_agent_prompt,
    tts_agent_prompt,
    final_result_prompt
    )

from langgraph.checkpoint.memory import InMemorySaver

from typing import Literal, Optional
import json
from datetime import datetime
import asyncio
from dotenv import load_dotenv


# Initialize a configurable model that we will use throughout the agent
configurable_model = init_chat_model(
    configurable_fields=("model", "temperature", "api_key"),
)
# 加载.env文件
load_dotenv()  # 等同于 load_dotenv(".env")

async def main_agent_logic(
    state: AgentState,
    config: RunnableConfig
) -> Command[Literal["generate_mnemonic", "generate_image", "generate_tts", "final_result"]]:
    """
    主智能体逻辑：
    - 根据用户输入和当前状态，生成决策 Decision
    - 返回最终结果 WordMemoryResult
    """
    # Step 1: Check if clarification is enabled in configuration
    configurable = EnglishAppConfig.from_runnable_config(config)

    # Step 2:Prepare the prompt with current state
    last_msg = state.get("messages", [])
    messages = last_msg[-1].content if last_msg else ""

    model_config = {
        "model": configurable.llm.main_agent_model,
        "temperature": configurable.llm.main_agent_temperature,
        "api_key": get_api_key_for_model(configurable.llm.main_agent_model, config)
    }

    # build json string of current state
    current_style_id = state.get("style_profile_id") or configurable.defaults.default_style_profile_id

    state_context = {
        "word": state.get("word"),
        "mnemonic": state.get("mnemonic"),
        "image_url": state.get("image_url"),
        "audio_url": state.get("audio_url"),
        "style_profile_id": current_style_id,
        "user_mnemonic_pref": to_dict_or_self(state.get("user_mnemonic_pref")) if state.get("user_mnemonic_pref") else None,
        "user_image_pref": to_dict_or_self(state.get("user_image_pref")) if state.get("user_image_pref") else None,
        "user_voice_pref": to_dict_or_self(state.get("user_voice_pref")) if state.get("user_voice_pref") else None,
        # 把上一轮的决策放入 context，帮助 LLM 理解连续对话
        "last_decision": state.get("last_decision") 
    }

    prompt = main_agent_prompt.replace(
        "{current_state_json}", 
        json.dumps(state_context, ensure_ascii=False)
    ).replace(
        "{user_input}", 
        messages
    )

    # Call the LLM to get the decision
    model = (
        configurable_model
        .with_structured_output(Decision)
        .with_retry(stop_after_attempt=configurable.retry.max_retries)
        .with_config(model_config)
    )

    decision = await model.ainvoke([HumanMessage(content=prompt)])

    # new_word 一定要有 mnemonic
    if decision.intent == "new_word":
        decision.need_new_mnemonic = True

    # Route based on the decision
    if decision.need_new_image and not configurable.features.enable_image_generation:
        decision.need_new_image = False
        decision.image_style = None
        decision.reason += " (Config禁止生成图片)"

    if decision.need_new_audio and not configurable.features.enable_tts_generation:
        decision.need_new_audio = False
        decision.voice_style = None
        decision.reason += " (Config禁止生成语音)"

    # 安全策略：如果 Config 不允许 strong_aggressive，但 style 选了 aggressive
    if (decision.style_profile_id == "aggressive" and not configurable.safety.allow_strong_aggressive):
        # 降级处理，或者在 mnemonic_style 里限制
        if decision.mnemonic_style and decision.mnemonic_style.humor == "aggressive":
             decision.mnemonic_style.humor = "dark" # 降级为 dark
             decision.reason += " (安全策略限制，降级为dark)"

    # 仅针对“新学单词”意图执行此策略
    if decision.intent == "new_word":
        # 🚨 策略 A: Unknown -> 熔断 (认定不是有效单词)
        if decision.difficulty == "unknown":
            # 强制修改意图为“无关/无法处理”，防止下游 Agent 浪费 Token
            decision.intent = "out_of_scope"
            
            # 关闭所有生成开关
            decision.need_new_mnemonic = False
            decision.need_new_image = False
            decision.need_new_audio = False
            
            # 记录原因，Final Result 节点可以据此生成提示文案
            decision.reason = "系统无法识别该输入为有效单词，或难度判定失败，停止生成。"

        # ✅ 策略 B: Medium / Hard -> 强制配图 (辅助记忆)
        elif decision.difficulty in ["medium", "hard"]:
            # 检查：如果功能开启，且当前未开启配图
            if configurable.features.enable_image_generation and not decision.need_new_image:
                decision.need_new_image = True
                decision.reason += f" [Strategy:监测到{decision.difficulty}难词，自动补充配图]"
                
                # 自动补全 Style (防止 LLM 给空值)
                if not decision.image_style:
                    # 优先取用户偏好，没有则取 Config 默认
                    default_style = state.get("user_image_pref")
                    if not default_style:
                        # 构造默认 ImageStyle (需导入 ImageStyle 类)
                        decision.image_style = ImageStyle(
                            need_image=True,
                            style=configurable.defaults.default_image_style,
                            mood=configurable.defaults.default_image_mood,
                            extra_tags=[]
                        )
                    else:
                        decision.image_style = default_style

        # 🛑 策略 C: Easy -> 强制不配图 (节省成本/保持清爽)
        elif decision.difficulty == "easy":
            # 即使 LLM 想要画，我们也强制关闭
            if decision.need_new_image:
                decision.need_new_image = False
                decision.image_style = None # 清空风格
                decision.reason += " [Strategy:简单词汇强制跳过配图]"

    # 5. 准备状态更新 (State Update)
    # 这些内容会立即写入 StateGraph 的 checkpoint
    had_existing_image = bool(state.get("image_url"))

    if decision.need_new_mnemonic:
        # Mnemonic/story 更新后，确保多媒体同步刷新
        if configurable.features.enable_tts_generation:
            decision.need_new_audio = True

        if configurable.features.enable_image_generation and (had_existing_image or decision.need_new_image):
            decision.need_new_image = True
            if not decision.image_style:
                decision.image_style = state.get("user_image_pref") or ImageStyle(
                    need_image=True,
                    style=configurable.defaults.default_image_style,
                    mood=configurable.defaults.default_image_mood,
                    extra_tags=[]
                )

    previous_word = state.get("word")
    resolved_word = decision.word or previous_word

    update_dict = {
        "decision": decision,
        "last_decision": decision.model_dump(), # 存一下给下一轮参考
        # 如果是新词，更新 word；否则保持原样
        "word": resolved_word,
        # 总是更新当前风格 ID
        "style_profile_id": decision.style_profile_id or current_style_id
    }

    # 如果 scope 是 session_default，我们还需要更新用户长期偏好
    # 注意：AgentState 定义里有 user_*_pref，这里进行写入
    if decision.scope == "session_default" and configurable.preferences.allow_update_preferences:
        if decision.mnemonic_style:
            update_dict["user_mnemonic_pref"] = decision.mnemonic_style
        if decision.image_style:
            update_dict["user_image_pref"] = decision.image_style
        if decision.voice_style:
            update_dict["user_voice_pref"] = decision.voice_style
    
    # 6. 核心路由逻辑 (Routing Logic)
    # 根据你的要求：优先生成谐音(Mnemonic)，然后才是 图片/语音
    
    # 场景 A: 需要生成新谐音 (new_word 或 refine_mnemonic)
    # 必须先去 mnemonic_agent，因为它产生的 story 是下游 image/tts 的输入
    if decision.need_new_mnemonic:
        return Command(
            update=update_dict,
            goto="generate_mnemonic"
        )

    # 场景 B: 不需要改文字，只改多媒体
    need_img = decision.need_new_image
    need_audio = decision.need_new_audio
    audio_flow = decision.audio_flow  # "parallel" | "after_image" | "audio_only"

    # 1) 既要图又要音
    if need_img and need_audio:
        if audio_flow == "parallel":
            # 并行：主 agent 直接并行调图 + 音
            return Command(
                update=update_dict,
                goto=["generate_image", "generate_tts"]
            )
        elif audio_flow == "after_image":
            # 串行：先图，generate_image 结束后再跳转到 TTS
            return Command(
                update=update_dict,
                goto="generate_image"
            )
        elif audio_flow == "audio_only":
            # 理论上不会出现“既要图又 audio_only”，这里兜底：只走语音
            return Command(
                update=update_dict,
                goto="generate_tts"
            )

    # 2) 只要图片
    if need_img and not need_audio:
        return Command(
            update=update_dict,
            goto="generate_image"
        )

    # 3) 只要语音
    if need_audio and not need_img:
        return Command(
            update=update_dict,
            goto="generate_tts"
        )

    # 4) 都不要：直接终点
    return Command(
        update=update_dict,
        goto="final_result"
    )
    
    # 场景 C: 不需要生成任何内容
    # 例如：intent="explain", "small_talk", "out_of_scope", "update_preferences"
    # 直接去终点（或者去一个回复生成的节点，这里简化为 final_result）
    return Command(
        update=update_dict,
        goto="final_result"
    )


async def generate_mnemonic(state: AgentState,
                            config: RunnableConfig) -> Command[Literal["generate_image", "generate_tts", "final_result"]]:
    """
    谐音梗智能体逻辑：
    - 根据主智能体的决策，生成新的谐音梗和场景故事
    - 返回更新后的状态，继续后续生成（图片/语音）或终点
    """
    # Step 1: Load configuration
    configurable = EnglishAppConfig.from_runnable_config(config)
    model_config = {
        "model": configurable.llm.mnemonic_agent_model,
        "temperature": configurable.llm.mnemonic_agent_temperature,
        "api_key": get_api_key_for_model(configurable.llm.mnemonic_agent_model, config)
    }

    decision = state.get("decision")

    # ========== 2. 确定目标单词 ==========
    # 优先使用 Decision 指派的新词；如果是 refine_mnemonic，则使用 state 中的旧词(state是记录当前单词的)
    target_word = decision.word if decision and decision.word else state.get("word")

    if not target_word:
        # 无法继续，直接跳到终点
        return Command(
            update={"reply_text": "系统错误：未找到目标单词。"},
            goto="final_result"
        )
    
    # ========== 3. 确定风格 (Style Resolution) ==========
    # 优先级：本轮决策 > 用户长期偏好 > 系统默认
    final_style = None

    # A. 检查本轮决策
    if decision and decision.mnemonic_style:
        final_style = decision.mnemonic_style
    
    # B. 检查用户偏好 (State)
    if not final_style and state.get("user_mnemonic_pref"):
        final_style = state.get("user_mnemonic_pref")
        
    # C. 使用 Config 默认兜底
    if not final_style:
        # 需导入 MnemonicStyle 模型
        final_style = MnemonicStyle(
            humor=configurable.defaults.default_mnemonic_humor,
            dialect=configurable.defaults.default_mnemonic_dialect,
            complexity="normal",
            extra_tags=[]
        )
    
    # ========== 4. 调用 LLM 生成 ==========
    model = (
        configurable_model
        .with_structured_output(WordBlock)
        .with_retry(stop_after_attempt=configurable.retry.max_retries)
        .with_config(model_config)
    )
    # 序列化风格参数
    style_json = json.dumps(final_style.model_dump(), ensure_ascii=False)
    formatted_prompt = mnemonic_agent_prompt.replace("{word}", target_word).replace("{mnemonic_style_json}", style_json)

    response = await model.ainvoke([HumanMessage(content=formatted_prompt)])

    # ========== 5. 准备状态更新 (State Update) ==========
    # 将完整结构存入 word_block_partial，方便 final_result 组装最终结果
    update_dict = {
        "word": target_word,
        "mnemonic": response.homophone.text,
        "scene_text": response.story,
        "meaning": response.meaning.cn,
        "word_block_partial": response
    }

    # ========== 6. 关键路由逻辑 (Routing) ==========
    # 任务已完成，现在查看 Main Agent 的原始决策，决定下一步去哪里
    if not decision:
        return Command(update=update_dict, goto="final_result")

    need_img = decision.need_new_image
    need_audio = decision.need_new_audio
    audio_flow = decision.audio_flow  # "parallel" | "after_image" | "audio_only"

    # 1) 图 + 声
    if need_img and need_audio:
        if audio_flow == "parallel":
            return Command(
                update=update_dict,
                goto=["generate_image", "generate_tts"]
            )
        elif audio_flow == "after_image":
            return Command(
                update=update_dict,
                goto="generate_image"
            )
        elif audio_flow == "audio_only":
            # 冲突兜底：只做语音
            return Command(
                update=update_dict,
                goto="generate_tts"
            )

    # 2) 只要图
    if need_img and not need_audio:
        return Command(
            update=update_dict,
            goto="generate_image"
        )

    # 3) 只要音频
    if need_audio and not need_img:
        return Command(
            update=update_dict,
            goto="generate_tts"
        )

    # 4) 都不要
    return Command(
        update=update_dict,
        goto="final_result"
    )

async def generate_image(state: AgentState,
                         config: RunnableConfig) -> Command[Literal["generate_tts", "final_result"]]:
    """图片生成智能体逻辑：
    - 根据主智能体的决策，生成新的图片
    - 返回更新后的状态，继续后续生成（语音）或终点
    """
    # Load configuration
    configurable = EnglishAppConfig.from_runnable_config(config)
    model_config = {
        "model": configurable.llm.main_agent_model,
        "temperature": configurable.llm.main_agent_temperature,
        "api_key": get_api_key_for_model(configurable.llm.main_agent_model, config)
    }

    decision = state.get("decision")
    
    # 1. 业务执行逻辑 (保持不变，生成图片)
    # 1.1 开关与数据校验
    should_skip = False
    if not configurable.features.enable_image_generation:
        print("🚫 [Image Agent] Disabled by config.")
        should_skip = True
    
    target_word = decision.word if decision and decision.word else state.get("word")
    scene_text = state.get("scene_text")
    if not scene_text:
        print("⚠️ [Image Agent] Missing scene_text. Skipping.")
        should_skip = True
    
    image_url = None

    # 1.2 如果不跳过，执行生成
    if not should_skip:
        # Style Resolution (本轮 > 用户偏好 > 默认)
        final_image_style = None
        if decision and decision.image_style:
            final_image_style = decision.image_style
        elif state.get("user_image_pref"):
            final_image_style = state.get("user_image_pref")
        else:
            final_image_style = ImageStyle(
                need_image=True,
                style=configurable.defaults.default_image_style,
                mood=configurable.defaults.default_image_mood,
                extra_tags=[]
            )
        
        # 调用 LLM 生成图片 Prompt
        model = (
            configurable_model
            .with_structured_output(ImageGenOutput)
            .with_retry(stop_after_attempt=configurable.retry.max_retries)
            .with_config(model_config)
        )
        style_json = json.dumps(final_image_style.model_dump(), ensure_ascii=False)
        formatted_prompt = image_agent_prompt.replace("{word}", target_word).replace("{scene_text}", scene_text).replace("{image_style_json}", style_json)

        response = await model.ainvoke([HumanMessage(content=formatted_prompt)])

        try:
            # 调用图片生成工具 (假设有一个 image_generation_tool 函数)
            image_url = await generate_image_tool(response.image_prompt, response.negative_prompt, json.loads(style_json), api_key=get_api_key_for_model("qwen", config))
        except Exception as e:
            print(f"❌ [Image Agent] Failed: {e}")
            # 图片失败不阻断流程，继续往下走
        
    # 2. 路由逻辑 (Routing Logic) - 核心修改
    update_dict = {}
    if image_url:
        update_dict["image_url"] = image_url
    
    # 4. 路由逻辑：
    #    只有在 audio_flow == "after_image" 的场景，才由图片节点串到 TTS
    need_audio = decision and decision.need_new_audio
    audio_enabled = configurable.features.enable_tts_generation
    audio_flow = decision.audio_flow if decision else "parallel"

    if need_audio and audio_enabled and audio_flow == "after_image":
        # 串行模式：图片完成后进入语音生成
        return Command(
            update=update_dict,
            goto="generate_tts"
        )
    else:
        # 并行模式（parallel）下，TTS 已由 main_agent 或 generate_mnemonic 并行触发；
        # 或者本轮根本不需要语音 → 直接汇总
        return Command(
            update=update_dict,
            goto="final_result"
        )


async def generate_tts(state: AgentState,
                       config: RunnableConfig) -> Command[Literal["final_result"]]:
    """语音生成智能体逻辑：
    - 根据主智能体的决策，生成新的语音
    - 返回更新后的状态，继续后续生成（最终结果）
    """
    # Load configuration
    configurable = EnglishAppConfig.from_runnable_config(config)
    model_config = {
        "model": configurable.llm.main_agent_model,
        "temperature": configurable.llm.main_agent_temperature,
        "api_key": get_api_key_for_model(configurable.llm.main_agent_model, config)
    }

    decision = state.get("decision")

    # 2. 开关校验 (Feature Flag)
    if not configurable.features.enable_tts_generation:
        print("🚫 [TTS Agent] Feature disabled by config.")
        return Command(goto="final_result")
    
    # 3. 数据准备 (Data Prep)
    target_word = decision.word if decision and decision.word else state.get("word")
    mnemonic_text = state.get("mnemonic")
    story_text = state.get("scene_text")

    if not (target_word and mnemonic_text and story_text):
        print(f"⚠️ [TTS Agent] Missing text components for '{target_word}'. Skipping.")
        return Command(
            update={"reply_text": "语音生成失败：缺少必要的文本内容。"},
            goto="final_result"
        )
    
    # 组合原始文本： 单词 + 谐音 + 故事
    full_raw_text = f"{target_word}。{mnemonic_text}。{story_text}"

    # 4. 确定语音风格 (Style Resolution)
    # 优先级：本轮决策 > 用户长期偏好 > 系统默认
    final_voice_style = None

    # A. 本轮决策
    if decision and decision.voice_style:
        final_voice_style = decision.voice_style
    
    # B. 用户偏好
    if not final_voice_style and state.get("user_voice_pref"):
        final_voice_style = state.get("user_voice_pref")
    
    # C. 系统默认
    if not final_voice_style:
        final_voice_style = VoiceStyle(
            gender=configurable.defaults.default_voice_gender,
            energy=configurable.defaults.default_voice_energy,
            pitch="medium",
            speed=configurable.defaults.default_voice_speed,
            tone="normal"
        )

    # 5. 调用 LLM 进行语音参数编排 (Director Logic)
    model = (
        configurable_model
        .with_structured_output(TTSGenOutput)
        .with_retry(stop_after_attempt=configurable.retry.max_retries)
        .with_config(model_config)
    )
    style_json = json.dumps(final_voice_style.model_dump(), ensure_ascii=False)
    formatted_prompt = tts_agent_prompt.replace("{word}", target_word)\
                                       .replace("{text}", full_raw_text)\
                                       .replace("{voice_style_json}", style_json)
    
    response = await model.ainvoke([HumanMessage(content=formatted_prompt)])

    # 6. 会员权益/权限降级 (Optional Business Logic)
    # 如果 Config 不允许高级语音，但 LLM 选了 dynamic 等高级音色，强制回退
    final_voice_id = response.voice_preset_id
    if not configurable.features.enable_premium_voices:
        # todo: 这里简单示例，实际可查表
        if "dynamic" in final_voice_id or "expressive" in final_voice_id:
             final_voice_id = "standard_neutral"
             print("ℹ️ [TTS Agent] Downgraded to standard voice due to config.")

    # 7. 调用 TTS 工具 (Tool Execution)
    audio_url = None

    try:
        # 调用语音生成工具 (假设有一个 generate_audio_tool 函数)
        audio_url = await tts_generation_tool(
            text=response.text_to_speak,
            api_key=get_api_key_for_model("qwen-tts", config)
            )
    except Exception as e:
        print(f"❌ [TTS Agent] Failed: {e}")
        # 语音失败不阻断流程，继续往下走

    # 8. 更新状态并汇聚
    # 指向 final_result，配合 LangGraph 并行机制
    return Command(
        update={
            "audio_url": audio_url,
            "audio_voice_profile_id": final_voice_id,  # 新字段
        },
        goto="final_result"
    )


async def final_result(state: AgentState,
                       config: RunnableConfig):
    """最终结果智能体逻辑：
    """
    # Load configuration
    configurable = EnglishAppConfig.from_runnable_config(config)
    model_config = {
        "model": configurable.llm.main_agent_model,
        "temperature": configurable.llm.main_agent_temperature,
        "api_key": get_api_key_for_model(configurable.llm.main_agent_model, config)
    }

    decision = state.get("decision")

    # 获取基础元数据
    intent = decision.intent if decision else "unknown"
    target_word = decision.word if decision and decision.word else state.get("word") or "unknown"
    current_style_id = state.get("style_profile_id") or configurable.defaults.default_style_profile_id

    # 准备最终输出的 Prompt
    """
    formatted_prompt = final_result_prompt\
    .replace("{intent}", intent)\
    .replace("{word}", target_word)\
    .replace("{style_profile_id}", current_style_id)\
    .replace("{mnemonic}", state.get("mnemonic") or "")\
    .replace("{scene_text}", state.get("scene_text") or "")\
    .replace("{meaning}", state.get("meaning") or "")

    """
    formatted_prompt = final_result_prompt.replace("{intent}", intent)\
                                          .replace("{word}", target_word)\
                                          .replace("{style_profile_id}", current_style_id)
    model = (
        configurable_model
        .with_structured_output(FinalReplyOutput)
        .with_retry(stop_after_attempt=configurable.retry.max_retries)
        .with_config(model_config)
    )

    response = await model.ainvoke([HumanMessage(content=formatted_prompt)])
    final_reply_text = response.reply_text

    # Small talk / Out of Scope: 不生成单词卡片
    if intent in ["out_of_scope", "small_talk"]:
        return Command(
            update={
                "reply_text": final_reply_text,
                "final_output": None
            },
            goto=END
        )
    
    # 构造最终的 WordMemoryResult
    # --- A. 组装 WordBlock ---
    partial = state.get("word_block_partial")

    if partial and isinstance(partial, WordBlock):
        word_block_obj = partial
    else:
        # 降级策略：如果 mnemonic 没运行(如只改图)，从 state 扁平字段拼凑
        # 这种情况下音标(ipa)可能会缺失，需给默认值
        word_block_obj = WordBlock(
            word=target_word,
            phonetic=Phonetic(ipa="", pronunciation_note=""),
            homophone=Homophone(
                text=state.get("mnemonic") or "生成中...",
                raw="",
                explanation=""
            ),
            story=state.get("scene_text") or "暂无故事",
            meaning=Meaning(
                pos="unknown",
                cn=state.get("meaning") or "暂无释义"
            )
        )
    
    # --- B. 组装 MediaBlock ---
    # 检查 Image
    img_obj = None
    if state.get("image_url"):
        # 尝试获取风格
        s_style = "comic" # 默认
        s_mood = "funny"
        if decision and decision.image_style:
            s_style = decision.image_style.style
            s_mood = decision.image_style.mood

        img_obj = ImageMedia(
            url=state.get("image_url"),
            style=s_style if s_style != "none" else "comic",
            mood=s_mood,
            updated_at=datetime.now().isoformat()
        )
    
    # 检查 Audio
    audio_obj = None
    if state.get("audio_url"):
        audio_obj = AudioMedia(
            url=state.get("audio_url"),
            voice_profile_id=state.get("audio_voice_profile_id"),
            duration_sec=0.0, # 需后端计算，此处占位
            updated_at=datetime.now().isoformat()
        )
    
    media_block_obj = MediaBlock(image=img_obj, audio=audio_obj)

    # --- C. 组装 StylesBlock ---
    styles_block_obj = StylesBlock(
        style_profile_id=current_style_id,
        mnemonic_style=decision.mnemonic_style if decision else None,
        image_style=decision.image_style if decision else None,
        voice_style=decision.voice_style if decision else None
    )

    # --- D. 组装 StatusBlock ---
    updated_parts_list = []
    reason_str = "Generated."
    scope_str = "this_turn"

    if decision:
        if decision.need_new_mnemonic: updated_parts_list.append("mnemonic")
        if decision.need_new_image: updated_parts_list.append("image")
        if decision.need_new_audio: updated_parts_list.append("audio")
        reason_str = decision.reason
        scope_str = decision.scope

    status_block_obj = StatusBlock(
        is_first_time=False, # 这里暂定False，实际业务需判断DB
        intent=intent,
        updated_parts=updated_parts_list,
        scope=scope_str,
        reason=reason_str
    )

    # 最终构建 WordMemoryResult
    final_result_obj = WordMemoryResult(
        type="word_memory",
        intent=intent,
        word_block=word_block_obj,
        media=media_block_obj,
        styles=styles_block_obj,
        status=status_block_obj
    )

    # 将 Pydantic 对象转为 Dict 存入 State (方便 JSON 序列化传给前端)
    return Command(
        update={
            "reply_text": final_reply_text,
            "final_output": final_result_obj
        },
        goto=END
    )


english_app_agent_graph = StateGraph(AgentState)
english_app_agent_graph.add_node("main_agent_logic", main_agent_logic)
english_app_agent_graph.add_node("generate_mnemonic", generate_mnemonic)
english_app_agent_graph.add_node("generate_image", generate_image)
english_app_agent_graph.add_node("generate_tts", generate_tts)
english_app_agent_graph.add_node("final_result", final_result)

english_app_agent_graph.add_edge(START, "main_agent_logic")
english_app_agent_graph.add_edge("final_result", END)

config = {"configurable": {"thread_id": "english_app_agent_thread"}}
checkpointer = InMemorySaver()

app_agent = english_app_agent_graph.compile(checkpointer=checkpointer)

async def run_agent():
    input_data = {
        "messages": [HumanMessage(content="帮我解释这个单词 'dependency' 并生成一个有趣的记忆方法。")],
    }
    result = await app_agent.ainvoke(input_data, config=config)
    print(result)

asyncio.run(run_agent())
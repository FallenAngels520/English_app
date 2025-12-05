from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
from typing_extensions import TypedDict


# 主要是对应 prompt 中的 DecisionOutput 结构
class MnemonicStyle(BaseModel):
    """谐音梗风格配置，用于指导谐音生成智能体。"""
    humor: Literal["none", "light", "dark", "aggressive"] = Field(
        "light", description="幽默强度/类型"
    )
    dialect: Literal["none", "mandarin", "dongbei", "cantonese"] = Field(
        "mandarin", description="方言风格"
    )
    complexity: Literal["simple", "normal", "complex"] = Field(
        "normal", description="谐音梗复杂度"
    )
    extra_tags: List[str] = Field(
        default_factory=list,
        description="额外风格标签，如“嘴臭”“东北梗”等"
    )

class ImageStyle(BaseModel):
    """图片风格配置，用于图像生成智能体。"""
    need_image: bool = Field(True, description="是否需要配图")
    style: Literal["none", "cute", "comic", "realistic", "anime"] = Field(
        "comic", description="图片风格"
    )
    mood: Literal["neutral", "funny", "dark", "warm"] = Field(
        "funny", description="图片情绪"
    )
    extra_tags: List[str] = Field(
        default_factory=list,
        description="额外风格标签，如“生活场景”“地铁”“医院”等"
    )

class VoiceStyle(BaseModel):
    """语音风格配置，用于 TTS 智能体。"""
    preset_id: Optional[str] = Field(
        default=None, description="TTS 预设 ID，若为空由后端映射"
    )
    gender: Literal["male", "female", "neutral"] = Field(
        "neutral", description="男声/女声/中性"
    )
    energy: Literal["low", "medium", "high"] = Field(
        "medium", description="情绪能量"
    )
    pitch: Literal["low", "medium", "high"] = Field(
        "medium", description="音高"
    )
    speed: Literal["slow", "normal", "fast"] = Field(
        "normal", description="语速"
    )
    tone: Literal["soft", "normal", "bright"] = Field(
        "normal", description="音色"
    )

class Decision(BaseModel):
    """
    主 Agent（主理人）的结构化决策输出。
    用于：
    - 表达用户意图（intent）
    - 告知后端/编排流程本轮需要生成哪些组件（谐音/图片/语音）
    - 给出对应的风格参数（mnemonic_style/image_style/voice_style）
    - 指明这些设置的作用范围（scope）
    """
    intent: Literal[
        "new_word",          # 输入新单词，生成完整记忆卡
        "refine_mnemonic",   # 换谐音梗
        "change_image",      # 换图片
        "change_audio",      # 换语音
        "update_preferences",# 更新长期偏好
        "explain",           # 解释当前谐音/故事/含义
        "small_talk",        # 闲聊，略相关但不需生成
        "out_of_scope",      # 与应用无关
    ] = Field(..., description="本轮主意图")

    # 当前目标单词（若本轮没提到但在评价当前结果，可以为 None，后端用 state 中的 word）
    word: Optional[str] = Field(
        default=None, description="本轮要处理的单词"
    )

    difficulty: Literal["easy", "medium", "hard", "unknown"] = Field(
        "unknown", description="主观难度判断，用于是否配图等策略"
    )

    # 风格档位（UI 可见，用于“清爽/搞笑/攻击性/东北梗”等模式）
    style_profile_id: Optional[
        Literal["simple_clean", "funny", "aggressive", "dongbei_funny", "other"]
    ] = Field(
        default=None,
        description="整体风格档位，用于 UI 显示和下游风格偏向"
    )

    # 本轮需要生成哪些组件
    need_new_mnemonic: bool = Field(
        False, description="是否需要重新生成谐音梗（及相关故事）"
    )
    need_new_image: bool = Field(
        False, description="是否需要生成/替换图片"
    )
    need_new_audio: bool = Field(
        False, description="是否需要生成/替换语音"
    )

    # 细粒度风格配置（当前决策层面的，若缺省则可以回退到用户长期偏好）
    mnemonic_style: Optional[MnemonicStyle] = Field(
        default=None,
        description="谐音梗生成的风格参数"
    )
    image_style: Optional[ImageStyle] = Field(
        default=None,
        description="图片生成的风格参数"
    )
    voice_style: Optional[VoiceStyle] = Field(
        default=None,
        description="语音合成的风格参数"
    )

    # 设置作用范围：仅当前轮次 or 作为会话/长期默认
    scope: Literal["this_turn", "session_default"] = Field(
        "this_turn",
        description="本次设置的作用范围：本轮生效或作为之后的默认偏好"
    )

    # 方便调试/埋点：用简短中文解释决策原因
    reason: str = Field(
        ...,
        description="简短中文，说明该决策的原因（例如“用户说谐音太冷，要求更有攻击性和东北话风格”）"
    )


# ---------- 最终输出结构：WordMemoryResult ----------

class Phonetic(BaseModel):
    """音标和发音提示。"""
    ipa: Optional[str] = Field(
        default=None,
        description="国际音标，例如 /ˈæmbjələns/"
    )
    pronunciation_note: Optional[str] = Field(
        default=None,
        description="用中文/拼音描述的发音提示，如“近似读音 'AM-byu-lens'”"
    )

class Homophone(BaseModel):
    """中文谐音梗本体。"""
    text: str = Field(
        ...,
        description="最终呈现给用户的中文谐音梗，例如“俺不能死”"
    )
    raw: Optional[str] = Field(
        default=None,
        description="拼音或更原始的读音表示，例如“an bu neng si”"
    )
    explanation: Optional[str] = Field(
        default=None,
        description="对谐音梗的简短说明，可选"
    )

class Meaning(BaseModel):
    """单词含义信息。"""
    pos: Optional[str] = Field(
        default=None,
        description="词性简写，如 'n.' 'v.' 'adj.'"
    )
    cn: str = Field(
        ...,
        description="核心中文释义，如“救护车”"
    )
    en: Optional[str] = Field(
        default=None,
        description="可选：英文释义/解释"
    )

# 这个是generate_mnemonic output_struct对应的结构
class WordBlock(BaseModel):
    """单词 + 谐音 + 场景 + 含义组成的主体内容。"""
    word: str = Field(..., description="英语单词")
    phonetic: Optional[Phonetic] = Field(
        default=None,
        description="音标和发音提示"
    )
    homophone: Homophone = Field(
        ...,
        description="中文谐音梗"
    )
    story: str = Field(
        ...,
        description="结合谐音梗的荒诞/生活化场景故事"
    )
    meaning: Meaning = Field(
        ...,
        description="单词的词性与含义"
    )

class ImageMedia(BaseModel):
    """图片媒体信息。"""
    url: str = Field(..., description="图片 URL")
    style: Literal["cute", "comic", "realistic", "anime", "none"] = Field(
        "comic", description="图片风格"
    )
    mood: Literal["neutral", "funny", "dark", "warm"] = Field(
        "funny", description="图片情绪"
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="ISO 时间字符串，图片最近更新时间"
    )

class AudioMedia(BaseModel):
    """语音媒体信息。"""
    url: str = Field(..., description="音频 URL")
    voice_profile_id: Optional[str] = Field(
        default=None,
        description="使用的语音预设 ID"
    )
    duration_sec: Optional[float] = Field(
        default=None,
        description="音频时长（秒）"
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="ISO 时间字符串，音频最近更新时间"
    )

class MediaBlock(BaseModel):
    """多媒体内容（图片 + 音频）。"""
    image: Optional[ImageMedia] = Field(
        default=None,
        description="配图信息（如果本轮未生成可为空）"
    )
    audio: Optional[AudioMedia] = Field(
        default=None,
        description="语音信息（如果本轮未生成可为空）"
    )

class StylesBlock(BaseModel):
    """本次结果实际使用的风格信息。"""
    style_profile_id: Optional[
        Literal["simple_clean", "funny", "aggressive", "dongbei_funny", "other"]
    ] = Field(
        default=None,
        description="整体风格档位"
    )
    mnemonic_style: Optional[MnemonicStyle] = Field(
        default=None,
        description="谐音梗风格配置"
    )
    image_style: Optional[ImageStyle] = Field(
        default=None,
        description="图片风格配置"
    )
    voice_style: Optional[VoiceStyle] = Field(
        default=None,
        description="语音风格配置"
    )

class StatusBlock(BaseModel):
    """本轮行为摘要，便于前端和日志使用。"""
    is_first_time: bool = Field(
        ...,
        description="该单词是否首次生成（对当前用户）"
    )
    intent: Literal[
        "new_word",
        "refine_mnemonic",
        "change_image",
        "change_audio",
        "update_preferences",
        "explain",
        "small_talk",
        "out_of_scope",
    ] = Field(
        ...,
        description="本轮主意图，与主 agent 的 intent 对齐"
    )
    updated_parts: List[Literal["mnemonic", "image", "audio"]] = Field(
        default_factory=list,
        description="本轮被更新的组件列表"
    )
    scope: Literal["this_turn", "session_default"] = Field(
        "this_turn",
        description="本轮设置影响范围"
    )
    reason: str = Field(
        ...,
        description="简短中文，说明本轮为何这样决策"
    )

# 对外 API / 前端约定的最终格式
class WordMemoryResult(BaseModel):
    """
    对外暴露的最终结果格式：
    - 一张“单词记忆卡片”所需的全部信息
    - + 一些元信息（风格/状态）
    """
    type: Literal["word_memory"] = Field(
        "word_memory", description="结果类型固定为 word_memory"
    )
    intent: Literal[
        "new_word",
        "refine_mnemonic",
        "change_image",
        "change_audio",
        "update_preferences",
        "explain",
        "small_talk",
        "out_of_scope",
    ] = Field(
        ...,
        description="本轮主意图"
    )
    word_block: WordBlock = Field(
        ..., description="单词 + 谐音 + 场景 + 含义"
    )
    media: MediaBlock = Field(
        default_factory=MediaBlock,
        description="图片和语音"
    )
    styles: StylesBlock = Field(
        default_factory=StylesBlock,
        description="本轮实际使用的风格配置"
    )
    status: StatusBlock = Field(
        ..., description="行为摘要和元信息"
    )

# state
class AgentInputState(MessagesState):
    """InputState is only 'messages'.
    用户输入，通常是保存在messages；是作为整个图的开始；
    """

class AgentState(MessagesState):
    """English App Agent State."""

    # —— 当前内容（针对当前单词）——
    word: Optional[str]
    mnemonic: Optional[str]          # 中文谐音文本
    scene_text: Optional[str]        # 荒诞/生活化场景故事
    meaning: Optional[str]           # 单词中文释义
    image_url: Optional[str]
    audio_url: Optional[str]

    # —— 决策相关 ——
    decision: Optional[Decision]     # 本轮主 agent 决策

    # —— 风格档位 & 长期偏好 ——
    style_profile_id: Optional[str]  # simple_clean / funny / aggressive / dongbei_funny / other

    user_mnemonic_pref: Optional[MnemonicStyle]
    user_image_pref: Optional[ImageStyle]
    user_voice_pref: Optional[VoiceStyle]

    # —— 其他：上一轮决策快照（可选）——
    last_decision: Optional[dict]

    reply_text: Optional[str]        # 给前端的文案（在 reply 节点设置）

    final_output: Optional[str]     # 最终输出结果（包含所有生成内容）

# 图片生成agent的输出结构
class ImageGenOutput(BaseModel):
    """对应 image_agent_prompt 的结构化输出"""
    image_prompt: str = Field(
        ..., 
        description="传给 DALL-E/Midjourney 的最终英文提示词，包含主体、环境、风格描述"
    )
    negative_prompt: Optional[str] = Field(
        "", 
        description="负面提示词，不希望出现的元素"
    )
    reason: str = Field(
        ..., 
        description="简短中文说明画面构思，用于调试或日志"
    )

# 语音生成agent的输出结构
class TTSGenOutput(BaseModel):
    """对应 tts_agent_prompt 的结构化输出"""
    text_to_speak: str = Field(
        ..., 
        description="优化后的朗读文本，包含停顿标记(如...)或标点"
    )
    voice_preset_id: str = Field(
        ..., 
        description="推断出的音色ID分类，如 'male_dynamic', 'female_soft'"
    )
    speed_rate: float = Field(
        1.0, 
        description="语速 (0.8 ~ 1.2)"
    )
    reason: str = Field(
        ..., 
        description="参数选择理由"
    )

# 最终的输出格式
class FinalReplyOutput(BaseModel):
    reply_text: str

# config parameters for the English learning app agent

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel


from typing import Optional, Literal, Any
from pydantic import BaseModel

import os
import json

# ========== 1. LLM 模型相关配置 ==========

class LLMConfig(BaseModel):
    main_agent_model: str = "deepseek-chat"
    """主代理人使用的模型"""

    mnemonic_agent_model: str = "deepseek-chat"
    """谐音梗智能体使用的模型"""

    main_agent_temperature: float = 0.0
    """主代理人温度（决策建议保持 0）"""

    mnemonic_agent_temperature: float = 0.7
    """谐音梗智能体温度（可以稍微高一点，便于出梗）"""

    request_timeout_seconds: int = 30
    """LLM 请求超时时间"""


# ========== 2. 功能开关（Feature Flags） ==========

class FeatureFlags(BaseModel):
    enable_image_generation: bool = True
    """是否启用图片生成功能"""

    enable_tts_generation: bool = True
    """是否启用 TTS 语音生成功能"""

    enable_premium_voices: bool = True
    """是否启用高级语音（影响会员逻辑）"""

    enable_aggressive_style: bool = True
    """是否允许 'aggressive' 攻击性谐音风格（可用于安全策略）"""


# ========== 3. 偏好相关配置 ==========

class PreferenceConfig(BaseModel):
    allow_update_preferences: bool = True
    """是否允许主代理人根据 scope=session_default 写入长期偏好"""

    auto_learn_style_from_usage: bool = True
    """是否根据用户多次选择/吐槽自动调整默认 style_profile_id"""

    max_preference_history: int = 50
    """用于统计风格习惯的历史交互数上限（可选，后续做习惯学习用）"""


# ========== 4. 默认风格配置（冷启动/无偏好时使用） ==========

class DefaultStyleConfig(BaseModel):
    default_style_profile_id: Literal[
        "simple_clean", "funny", "aggressive", "dongbei_funny", "other"
    ] = "funny"
    """冷启动时的默认谐音风格档位"""

    default_mnemonic_humor: Literal["none", "light", "dark", "aggressive"] = "light"
    """冷启动默认谐音幽默程度"""

    default_mnemonic_dialect: Literal["none", "mandarin", "dongbei", "cantonese"] = "mandarin"
    """冷启动默认方言"""

    default_image_style: Literal["none", "cute", "comic", "realistic", "anime"] = "comic"
    """冷启动默认图片风格"""

    default_image_mood: Literal["neutral", "funny", "dark", "warm"] = "funny"
    """冷启动默认图片情绪"""

    default_voice_gender: Literal["male", "female", "neutral"] = "neutral"
    """冷启动默认语音性别"""

    default_voice_speed: Literal["slow", "normal", "fast"] = "normal"
    """冷启动默认语速"""

    default_voice_energy: Literal["low", "medium", "high"] = "medium"
    """冷启动默认语音能量"""

    default_voice_preset_id: Optional[str] = None
    """冷启动默认 TTS 预设ID（如 'free_male_1'）"""


# ========== 5. 安全和边界（特别是攻击性/敏感内容） ==========

class SafetyConfig(BaseModel):
    allow_dark_humor: bool = True
    """是否允许 'dark' 黑色幽默风格"""

    allow_strong_aggressive: bool = False
    """
    是否允许极强攻击性（比如非常嘴臭的梗）；
    如果 False，主代理人可将用户要求的 '攻击性' 收敛为 'light/dark'。
    """

    max_story_length_chars: int = 300
    """谐音故事最大长度建议（主代理人可在 reason 或 extra_tags 中提示下游控制）"""


# ========== 6. 重试 & 超时 ==========

class RetryConfig(BaseModel):
    max_retries: int = 3
    """最大重试次数"""

    retry_delay_seconds: int = 2
    """重试间隔时间（秒）"""


# ========== 7. 汇总配置 ==========

class EnglishAppConfig(BaseModel):
    """Configuration for English Mnemonic App."""

    llm: LLMConfig = LLMConfig()
    features: FeatureFlags = FeatureFlags()
    preferences: PreferenceConfig = PreferenceConfig()
    defaults: DefaultStyleConfig = DefaultStyleConfig()
    safety: SafetyConfig = SafetyConfig()
    retry: RetryConfig = RetryConfig()

    # 你原来的这个可以保留或并入 PreferenceConfig
    update_preferences: bool = True
    """全局开关：是否允许主代理人写入/更新用户长期偏好"""

    @classmethod
    def from_runnable_config(cls, config: RunnableConfig) -> "EnglishAppConfig":
        """从 LangGraph 的 RunnableConfig 创建 EnglishAppConfig 实例"""
        """Create a Configuration instance from a RunnableConfig."""
        configurable = config.get("configurable", {}) if config else {}
        field_names = list(cls.model_fields.keys())
        values: dict[str, Any] = {
            field_name: os.environ.get(field_name.upper(), configurable.get(field_name))
            for field_name in field_names
        }

        return cls(**{k: v for k, v in values.items() if v is not None})
    
    class Config:
        """Pydantic configuration."""
        
        arbitrary_types_allowed = True

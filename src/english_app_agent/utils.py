from langchain_core.runnables import RunnableConfig
import os


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
        elif model_name.startswith("anthropic:"):
            return os.getenv("ANTHROPIC_API_KEY")
        elif model_name.startswith("google"):
            return os.getenv("DEEPSEEK_API_KEY")
        return None
    
async def generate_image_tool(prompt: str, config_style: dict):
    # todo: implement image generation logic here
    pass 


async def tts_generation_tool(text: str, voice_profile_id: str, speed: float):
    # todo: implement tts generation logic here
    pass
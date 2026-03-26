import logging
from functools import lru_cache

from openai import AsyncOpenAI, OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ENTERPRISE HARD RULES: Strictly local vLLM API - Daten verlassen den Server nie!
MODEL_NAME = "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"


@lru_cache()
def get_async_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        base_url=settings.REQUIRED_VLLM_BASE_URL,
        api_key=settings.VLLM_API_KEY,
    )


@lru_cache()
def get_sync_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url=settings.REQUIRED_VLLM_BASE_URL,
        api_key=settings.VLLM_API_KEY,
    )


async def generate_text(messages: list[dict], temperature: float = 0.2) -> str:
    """Generiert Text über den lokalen vLLM Endpunkt."""
    try:
        response = await get_async_client().chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"VLLM Connection Error: {str(e)}")
        return "FEHLER: Der lokale KI-Server antwortet nicht."


def generate_text_sync(messages: list[dict], temperature: float = 0.2) -> str:
    """Generiert Text synchron über den lokalen vLLM Endpunkt."""
    try:
        response = get_sync_client().chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"VLLM Connection Error: {str(e)}")
        return "FEHLER: Der lokale KI-Server antwortet nicht."


async def generate_vision(
    prompt: str,
    base64_image: str,
    system_prompt: str = "Du bist ein hilfreicher KI-Assistent.",
    temperature: float = 0.2,
) -> str:
    """Verarbeitet Bilder streng lokal. Erzwingt 'detail: high' für Qwen."""
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "high",  # CRITICAL: Verhindert Pixelbrei!
                    },
                },
            ],
        },
    ]
    try:
        response = await get_async_client().chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"VLLM Vision Error: {str(e)}")
        return "FEHLER: Bild konnte nicht lokal verarbeitet werden."


def generate_vision_sync(
    prompt: str,
    base64_image: str,
    system_prompt: str = "Du bist ein hilfreicher KI-Assistent.",
    temperature: float = 0.2,
) -> str:
    """Verarbeitet Bilder synchron und streng lokal. Erzwingt 'detail: high' für Qwen."""
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "high",
                    },
                },
            ],
        },
    ]
    try:
        response = get_sync_client().chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"VLLM Vision Error: {str(e)}")
        return "FEHLER: Bild konnte nicht lokal verarbeitet werden."

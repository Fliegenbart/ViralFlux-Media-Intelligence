import os
import logging
from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)

# ENTERPRISE HARD RULES: Strictly local vLLM API - Daten verlassen den Server nie!
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "local")
MODEL_NAME = "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"

# Initialisiere den OpenAI Client als Wrapper für den lokalen vLLM
client = AsyncOpenAI(
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY,
)

sync_client = OpenAI(
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY,
)


async def generate_text(messages: list[dict], temperature: float = 0.2) -> str:
    """Generiert Text über den lokalen vLLM Endpunkt."""
    try:
        response = await client.chat.completions.create(
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
        response = sync_client.chat.completions.create(
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
        response = await client.chat.completions.create(
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
        response = sync_client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"VLLM Vision Error: {str(e)}")
        return "FEHLER: Bild konnte nicht lokal verarbeitet werden."

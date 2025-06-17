import openai
import os
import asyncio
from utils.logger import logger


def init_openai_api():
    """Set up the OpenAI API key from environment variables and warn if missing."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY не вказано у файлі .env або змінних оточення")
    openai.api_key = api_key
    return api_key


async def call_openai_chat(
    messages: list[dict],
    model: str = "gpt-3.5-turbo",
    max_tokens: int = 200,
    temperature: float = 0.9,
    timeout: int = 15,
    retries: int = 2,
) -> str:
    """Call the OpenAI chat completion API with retries and timeout."""
    for attempt in range(1, retries + 1):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    openai.chat.completions.create,
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ),
                timeout=timeout,
            )
            return response.choices[0].message.content.strip()
        except (openai.OpenAIError, asyncio.TimeoutError) as e:
            logger.error(f"❌ Помилка OpenAI (спроба {attempt}): {e}")
            if attempt == retries:
                raise
            await asyncio.sleep(1)



__all__ = ["init_openai_api", "call_openai_chat"]

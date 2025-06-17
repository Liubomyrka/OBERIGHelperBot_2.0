import openai
import os
import asyncio
from utils.logger import logger

ASSISTANT_ID = None


def init_openai_api():
    """Set up the OpenAI API key from environment variables and warn if missing."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY не вказано у файлі .env або змінних оточення")
    openai.api_key = api_key

    global ASSISTANT_ID
    ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
    return ASSISTANT_ID


def get_openai_assistant_id() -> str | None:
    """Return the assistant ID if set."""
    return ASSISTANT_ID


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


async def call_openai_assistant(
    messages: list[dict],
    assistant_id: str,
    timeout: int = 15,
    retries: int = 2,
) -> str:
    """Call the OpenAI Assistants API with retries and timeout."""
    for attempt in range(1, retries + 1):
        try:
            thread = await asyncio.wait_for(
                asyncio.to_thread(openai.beta.threads.create), timeout=timeout
            )
            for msg in messages:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        openai.beta.threads.messages.create,
                        thread_id=thread.id,
                        role=msg["role"],
                        content=msg["content"],
                    ),
                    timeout=timeout,
                )
            run = await asyncio.wait_for(
                asyncio.to_thread(
                    openai.beta.threads.runs.create,
                    thread_id=thread.id,
                    assistant_id=assistant_id,
                ),
                timeout=timeout,
            )
            while True:
                run = await asyncio.wait_for(
                    asyncio.to_thread(
                        openai.beta.threads.runs.retrieve,
                        thread_id=thread.id,
                        run_id=run.id,
                    ),
                    timeout=timeout,
                )
                if run.status == "completed":
                    msgs = await asyncio.wait_for(
                        asyncio.to_thread(
                            openai.beta.threads.messages.list,
                            thread_id=thread.id,
                        ),
                        timeout=timeout,
                    )
                    return (
                        msgs.data[0].content[0].text.value.strip()
                        if msgs.data
                        else ""
                    )
                if run.status in {"failed", "cancelled", "expired"}:
                    raise openai.OpenAIError(f"run {run.status}")
                await asyncio.sleep(1)
        except (openai.OpenAIError, asyncio.TimeoutError) as e:
            logger.error(f"❌ Помилка OpenAI Assistant (спроба {attempt}): {e}")
            if attempt == retries:
                raise
            await asyncio.sleep(1)



__all__ = [
    "init_openai_api",
    "call_openai_chat",
    "call_openai_assistant",
    "get_openai_assistant_id",
]

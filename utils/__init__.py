import openai
import os


def init_openai_api():
    """Set up the OpenAI API key from environment variables."""
    openai.api_key = os.getenv("OPENAI_API_KEY")


__all__ = ["init_openai_api"]

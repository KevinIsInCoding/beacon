import os
from abc import ABC, abstractmethod

import anthropic
import openai


def _normalize_messages(messages: list) -> list[dict]:
    """Convert LangGraph/LangChain message objects or dicts to {role, content} dicts."""
    result = []
    for msg in messages:
        if hasattr(msg, "type"):
            raw_role, content = msg.type, msg.content
        else:
            raw_role, content = msg.get("role", "user"), msg.get("content", "")

        if raw_role in ("human", "user"):
            role = "user"
        elif raw_role in ("ai", "assistant"):
            role = "assistant"
        else:
            continue

        result.append({"role": role, "content": content})
    return result


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, messages: list, system: str = "") -> str: ...


class AnthropicProvider(LLMProvider):
    MODEL = "claude-opus-4-7"

    def __init__(self):
        self._client = anthropic.Anthropic()

    def complete(self, messages: list, system: str = "") -> str:
        kwargs = dict(
            model=self.MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            messages=_normalize_messages(messages),
        )
        if system:
            kwargs["system"] = system
        with self._client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()
        return next((b.text for b in response.content if b.type == "text"), "")


class OpenAIProvider(LLMProvider):
    MODEL = "gpt-4o"

    def __init__(self):
        self._client = openai.OpenAI()

    def complete(self, messages: list, system: str = "") -> str:
        normalized = _normalize_messages(messages)
        if system:
            normalized = [{"role": "system", "content": system}] + normalized
        response = self._client.chat.completions.create(
            model=self.MODEL,
            messages=normalized,
        )
        return response.choices[0].message.content or ""


def get_provider(name: str | None = None) -> LLMProvider:
    name = name or os.getenv("LLM_PROVIDER", "anthropic")
    if name == "openai":
        return OpenAIProvider()
    if name == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}. Choose 'anthropic' or 'openai'.")

"""LLM provider abstraction: Groq (gpt-oss-120b) primary, Azure OpenAI fallback on 429/5xx.

Messages/tool-calls use plain dicts (not langchain BaseMessage) so the fake test client
doesn't need to fake langchain's message classes:
    message: {"role": "system"|"user"|"assistant"|"tool", "content": str, "tool_calls"?: [...], "tool_call_id"?: str, "name"?: str}
    tool schema: {"name": str, "description": str, "parameters": {json-schema}}
"""
from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int = 0


class LLMClient(abc.ABC):
    @abc.abstractmethod
    async def acomplete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse: ...


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return status == 429 or status >= 500
    # some SDKs stash it in the message
    text = str(exc)
    return "429" in text or "rate limit" in text.lower() or "503" in text or "502" in text


def _to_langchain_messages(messages: list[dict[str, Any]]):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    out = []
    for m in messages:
        role = m["role"]
        if role == "system":
            out.append(SystemMessage(content=m["content"]))
        elif role == "user":
            out.append(HumanMessage(content=m["content"]))
        elif role == "assistant":
            out.append(
                AIMessage(
                    content=m.get("content") or "",
                    tool_calls=[
                        {"name": tc["name"], "args": tc["args"], "id": tc["id"]}
                        for tc in m.get("tool_calls", [])
                    ],
                )
            )
        elif role == "tool":
            out.append(ToolMessage(content=m["content"], tool_call_id=m["tool_call_id"], name=m.get("name", "")))
    return out


def _tool_schemas_to_langchain(tools: list[dict[str, Any]] | None):
    if not tools:
        return None
    return [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
        for t in tools
    ]


class GroqAzureLLM(LLMClient):
    """Real provider: ChatGroq primary, AzureChatOpenAI fallback on 429/5xx."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._groq = None
        self._azure = None

    def _get_groq(self):
        if self._groq is None:
            from langchain_groq import ChatGroq

            self._groq = ChatGroq(model=self._settings.GROQ_MODEL, api_key=self._settings.GROQ_API_KEY)
        return self._groq

    def _get_azure(self):
        if self._azure is None:
            if not self._settings.AZURE_OPENAI_API_KEY:
                return None
            from langchain_openai import AzureChatOpenAI

            self._azure = AzureChatOpenAI(
                api_key=self._settings.AZURE_OPENAI_API_KEY,
                azure_endpoint=self._settings.AZURE_OPENAI_ENDPOINT,
                azure_deployment=self._settings.AZURE_OPENAI_DEPLOYMENT,
                api_version=self._settings.AZURE_OPENAI_API_VERSION,
            )
        return self._azure

    async def _invoke(self, model, messages, tools):
        lc_messages = _to_langchain_messages(messages)
        lc_tools = _tool_schemas_to_langchain(tools)
        bound = model.bind_tools(lc_tools) if lc_tools else model
        ai_msg = await bound.ainvoke(lc_messages)
        tool_calls = [
            ToolCall(id=tc.get("id") or uuid.uuid4().hex, name=tc["name"], args=tc.get("args", {}))
            for tc in getattr(ai_msg, "tool_calls", []) or []
        ]
        usage = getattr(ai_msg, "usage_metadata", None) or {}
        tokens = int(usage.get("total_tokens", 0)) if usage else 0
        return LLMResponse(content=ai_msg.content or "", tool_calls=tool_calls, tokens=tokens)

    async def acomplete(self, messages, tools=None) -> LLMResponse:
        try:
            return await self._invoke(self._get_groq(), messages, tools)
        except Exception as exc:  # noqa: BLE001 - provider-agnostic fallback
            if not _is_retryable(exc):
                raise
            azure = self._get_azure()
            if azure is None:
                raise
            return await self._invoke(azure, messages, tools)


class FakeLLM(LLMClient):
    """Deterministic stub for tests. Never calls a real API.

    `responder` is invoked with (messages, tools) and must return an LLMResponse.
    Defaults to a canned "final answer" that never calls tools, so specialist
    agents terminate immediately unless a test supplies a custom responder.
    """

    def __init__(self, responder: Callable[[list[dict], list[dict] | None], LLMResponse] | None = None):
        self.calls: list[tuple[list[dict], list[dict] | None]] = []
        self._responder = responder or (lambda messages, tools: LLMResponse(content="ok", tokens=1))

    async def acomplete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return self._responder(messages, tools)


def build_llm(settings: Settings) -> LLMClient:
    if settings.TESTING or not settings.GROQ_API_KEY:
        return FakeLLM()
    return GroqAzureLLM(settings)

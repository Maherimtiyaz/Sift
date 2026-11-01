from copy import deepcopy
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .providers import DEMO_RESULT, ProviderConfigurationError, groq_api_key, is_demo_mode, llm_provider

SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "due": {"type": "string"}, "src": {"type": "string"}},
            "required": ["text"]}},
        "events": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": "YYYY-MM-DDTHH:MM or empty"},
            "durationMin": {"type": "integer"},
            "when": {"type": "string"}, "src": {"type": "string"}}, "required": ["title"]}},
        "messages": {"type": "array", "items": {"type": "object", "properties": {
            "to": {"type": "string"}, "body": {"type": "string"}, "src": {"type": "string"}},
            "required": ["body"]}},
    },
    "required": ["tasks", "events", "messages"],
}


def _system_prompt(tz: str) -> str:
    now = datetime.now(ZoneInfo(tz))
    return (
        f"Today is {now:%A, %d %B %Y}, timezone {tz}. The user dictated a messy voice note. "
        "Sort it into tasks (short imperative to-dos), events (resolve relative dates to ISO "
        "using today's date) and messages (first-person drafts with the recipient). "
        "Never invent items. An item that is both a task and a message is a message only. "
        "For every item, set src to the exact words (max 10) copied from the note that it came from. "
        "Return only a JSON object matching this schema: "
        f"{json.dumps(SCHEMA)}"
    )


def _validated_result(value: object) -> dict:
    required = {"tasks": "text", "events": "title", "messages": "body"}
    if not isinstance(value, dict):
        raise ValueError("The AI provider returned an invalid sorted-note response.")
    for key, field in required.items():
        items = value.get(key)
        if not isinstance(items, list) or any(
            not isinstance(item, dict) or not isinstance(item.get(field), str)
            for item in items
        ):
            raise ValueError("The AI provider returned an invalid sorted-note response.")
    return value


async def _extract_anthropic(transcript: str, tz: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ProviderConfigurationError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic.")
    from anthropic import AsyncAnthropic

    resp = await AsyncAnthropic(api_key=api_key).messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=1500,
        system=_system_prompt(tz),
        tools=[{"name": "save_sorted_note", "description": "Save the sorted note.", "input_schema": SCHEMA}],
        tool_choice={"type": "tool", "name": "save_sorted_note"},
        messages=[{"role": "user", "content": transcript}],
    )
    block = next((block for block in resp.content if block.type == "tool_use"), None)
    if block is None:
        raise ValueError("Anthropic did not return a sorted-note response.")
    return _validated_result(block.input)


async def _extract_openai_compatible(
    transcript: str, tz: str, *, url: str, model: str, api_key: str | None = None,
) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            url,
            headers=headers,
            json={
                "model": model,
                "temperature": 0.2,
                "max_tokens": 1500,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _system_prompt(tz)},
                    {"role": "user", "content": transcript},
                ],
            },
        )
    response.raise_for_status()
    choices = response.json().get("choices", [])
    if not choices or not isinstance(choices[0].get("message", {}).get("content"), str):
        raise ValueError("The AI provider did not return a sorted-note response.")
    return _validated_result(json.loads(choices[0]["message"]["content"]))


async def extract(transcript: str, tz: str) -> dict:
    if is_demo_mode():
        return deepcopy(DEMO_RESULT)

    provider = llm_provider()
    if provider == "anthropic":
        return await _extract_anthropic(transcript, tz)
    if provider == "groq":
        return await _extract_openai_compatible(
            transcript, tz,
            url="https://api.groq.com/openai/v1/chat/completions",
            model=os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile"),
            api_key=groq_api_key(),
        )
    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        return await _extract_openai_compatible(
            transcript, tz,
            url=f"{base_url}/chat/completions",
            model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        )
    raise ProviderConfigurationError(f"Unsupported LLM_PROVIDER: {provider}.")

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropic

client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

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


async def extract(transcript: str, tz: str) -> dict:
    now = datetime.now(ZoneInfo(tz))
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=(
            f"Today is {now:%A, %d %B %Y}, timezone {tz}. The user dictated a messy voice note. "
            "Sort it into tasks (short imperative to-dos), events (resolve relative dates to ISO "
            "using today's date) and messages (first-person drafts with the recipient). "
            "Never invent items. An item that is both a task and a message is a message only. "
            "For every item, set src to the exact words (max 10) copied from the note that it came from."
        ),
        tools=[{"name": "save_sorted_note", "description": "Save the sorted note.", "input_schema": SCHEMA}],
        tool_choice={"type": "tool", "name": "save_sorted_note"},
        messages=[{"role": "user", "content": transcript}],
    )
    return next(b.input for b in resp.content if b.type == "tool_use")

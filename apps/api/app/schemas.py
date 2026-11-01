from typing import Literal

from pydantic import BaseModel

from .db import Item, Note

Kind = Literal["task", "event", "message"]


class ItemPatch(BaseModel):
    done: bool | None = None
    kind: Kind | None = None  # move the item to another list
    data: dict[str, str | int | None] | None = None  # edit fields, checked per kind in routers/items.py


def item_out(i: Item) -> dict:
    return {"id": i.id, "kind": i.kind, "done": i.done, **i.data}


def note_out(n: Note) -> dict:
    def pick(kind: str):
        return [{"id": i.id, "done": i.done, **i.data} for i in n.items if i.kind == kind]

    return {"id": str(n.id), "transcript": n.transcript, "created_at": n.created_at,
            "tasks": pick("task"), "events": pick("event"), "messages": pick("message")}

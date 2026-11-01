export type Task = { id: number; done: boolean; text: string; due?: string; src?: string };
export type Ev = {
  id: number; done: boolean; title: string; start?: string; durationMin?: number;
  when?: string; src?: string; tz?: string; google_link?: string;
};
export type Msg = { id: number; done: boolean; to?: string; body: string; src?: string };
export type Note = {
  id: string; transcript: string; created_at: string; tasks: Task[]; events: Ev[]; messages: Msg[];
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch("/api" + path, init);
  if (res.status === 401) {
    await fetch("/api/auth/logout", { method: "POST" });
    location.href = "/login";
    throw new Error("Please sign in again");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
});

export const api = {
  createNote: (fd: FormData) => call<Note>("/notes", { method: "POST", body: fd }),
  listNotes: () => call<Note[]>("/notes"),
  deleteNote: (id: string) => call<void>(`/notes/${id}`, { method: "DELETE" }),
  toggle: (id: number, done: boolean) =>
    call<{ id: number; done: boolean }>(`/items/${id}`, { ...json({ done }), method: "PATCH" }),
  syncEvent: (id: number, start?: string) =>
    call<{ link?: string }>(`/items/${id}/calendar`, json(start ? { start } : {})),
  patchItem: (id: number, body: ItemPatch) => call<ItemOut>(`/items/${id}`, { ...json(body), method: "PATCH" }),
  deleteItem: (id: number) => call<void>(`/items/${id}`, { method: "DELETE" }),
  liveConfig: () => call<{ wsUrl: string; demoMode: boolean }>("/live-config"),
  wsTicket: () => call<{ ticket: string }>("/ws-ticket", { method: "POST" }),
  googleStatus: () => call<{ connected: boolean; email: string | null }>("/google/status"),
  googleConnect: () => call<{ url: string }>("/google/connect"),
  googleDisconnect: () => call<void>("/google", { method: "DELETE" }),
};

export type ItemKind = "task" | "event" | "message";
export type ItemPatch = { done?: boolean; kind?: ItemKind; data?: Record<string, string | number | null> };
export type ItemOut = { id: number; kind: ItemKind; done: boolean; [field: string]: unknown };

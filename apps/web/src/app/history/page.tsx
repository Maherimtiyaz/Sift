"use client";
import { useEffect, useState } from "react";
import Results from "@/components/Results";
import { api, type Note } from "@/lib/api";

export default function History() {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => { api.listNotes().then(setNotes).catch((e: Error) => setErr(e.message)); }, []);

  async function remove(id: string) {
    await api.deleteNote(id);
    setNotes((n) => n && n.filter((x) => x.id !== id));
  }

  return (
    <main className="page">
      <h1 className="h1s">History</h1>
      {err && <div className="err" role="alert">{err}</div>}
      {notes?.length === 0 && <p className="empty">No notes yet. Record your first one.</p>}
      {notes?.map((n) => (
        <details className="hnote" key={n.id}>
          <summary>{new Date(n.created_at).toLocaleString([], { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })} · {n.transcript.slice(0, 70)}…</summary>
          <Results note={n} />
          <button className="ibtn" onClick={() => remove(n.id)}>Delete note</button>
        </details>
      ))}
    </main>
  );
}

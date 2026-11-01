"use client";
import Link from "next/link";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { api, type Ev, type ItemOut, type ItemPatch, type Msg, type Note, type Task } from "@/lib/api";

const KEYS = ["tasks", "events", "messages"] as const;
type K = (typeof KEYS)[number];
type Lists = { tasks: Task[]; events: Ev[]; messages: Msg[] };
type AnyItem = Task | Ev | Msg;
const KIND = { tasks: "task", events: "event", messages: "message" } as const;
const KEY_OF = { task: "tasks", event: "events", message: "messages" } as const;
const TEXT = { tasks: "text", events: "title", messages: "body" } as const;
const cap = (k: string) => k[0].toUpperCase() + k.slice(1);
const textOf = (k: K, x: AnyItem) => (x as unknown as Record<string, string>)[TEXT[k]] ?? "";

function Lane({ k, tab, color, count, children }: { k: K; tab: K; color: string; count: number; children: ReactNode }) {
  return (
    <section className={`lane${tab === k ? " on" : ""}`} style={{ "--a": color } as CSSProperties}>
      <div className="lh"><span className="dot" /><h2>{k === "messages" ? "Draft message" : cap(k)}</h2><span className="n">{count || ""}</span></div>
      {count === 0 && <div className="empty">Nothing here. Your note didn’t mention any.</div>}
      {children}
    </section>
  );
}

export default function Results({ note }: { note: Note }) {
  const [lists, setLists] = useState<Lists>({ tasks: note.tasks, events: note.events, messages: note.messages });
  const [tab, setTab] = useState<K>("tasks");
  const [src, setSrc] = useState("");
  const [links, setLinks] = useState<Record<number, string>>({});
  const [times, setTimes] = useState<Record<number, string>>({});
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(0);
  const [rev, setRev] = useState(0); // bumping this remounts rows, which resets any text the server rejected
  const [toast, setToast] = useState<{ msg: string; undo?: () => void } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const n = { tasks: lists.tasks.length, events: lists.events.length, messages: lists.messages.length };

  useEffect(() => { box.current?.querySelector("mark")?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [src]);
  // leaving the page finishes any delete that was still waiting for its undo window
  useEffect(() => () => { timers.current.forEach((t, id) => { clearTimeout(t); api.deleteItem(id).catch(() => {}); }); }, []);

  const q = src.trim(), at = q ? note.transcript.toLowerCase().indexOf(q.toLowerCase()) : -1;

  function apply(it: ItemOut) {
    const k = KEY_OF[it.kind];
    setLists((l) => {
      const cur = l[k] as AnyItem[];
      const had = cur.some((x) => x.id === it.id);
      const next = had ? cur.map((x) => (x.id === it.id ? (it as unknown as AnyItem) : x)) : [...cur, it as unknown as AnyItem];
      const strip = (arr: AnyItem[]) => arr.filter((x) => x.id !== it.id);
      return { tasks: strip(l.tasks), events: strip(l.events), messages: strip(l.messages), [k]: next } as unknown as Lists;
    });
  }

  async function patch(id: number, body: ItemPatch, moveTo?: K) {
    setErr("");
    try {
      apply(await api.patchItem(id, body));
      if (moveTo) setTab(moveTo);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn’t save that change");
      setRev((r) => r + 1);
    }
  }

  function toggle(id: number, done: boolean) {
    setLists((l) => ({ ...l, tasks: l.tasks.map((x) => (x.id === id ? { ...x, done } : x)) }));
    api.patchItem(id, { done }).catch(() => setLists((l) => ({ ...l, tasks: l.tasks.map((x) => (x.id === id ? { ...x, done: !done } : x)) })));
  }

  function remove(k: K, x: AnyItem) {
    const idx = (lists[k] as AnyItem[]).findIndex((y) => y.id === x.id);
    setLists((l) => ({ ...l, [k]: (l[k] as AnyItem[]).filter((y) => y.id !== x.id) }) as unknown as Lists);
    const t = setTimeout(() => {
      timers.current.delete(x.id);
      setToast(null);
      api.deleteItem(x.id).catch(() => setErr("Couldn’t delete that item"));
    }, 5000);
    timers.current.set(x.id, t);
    setToast({
      msg: "Deleted",
      undo: () => {
        clearTimeout(t);
        timers.current.delete(x.id);
        setLists((l) => {
          const cur = [...(l[k] as AnyItem[])];
          cur.splice(Math.min(idx, cur.length), 0, x);
          return { ...l, [k]: cur } as unknown as Lists;
        });
        setToast(null);
      },
    });
  }

  async function sync(id: number) {
    setErr("");
    try { const r = await api.syncEvent(id, times[id]); setLinks((l) => ({ ...l, [id]: r.link ?? "https://calendar.google.com" })); }
    catch (e) { setErr(e instanceof Error ? e.message : "Sync failed"); }
  }

  const editable = (k: K, x: AnyItem, locked = false) => (
    <span
      contentEditable={locked ? false : "plaintext-only"} suppressContentEditableWarning role="textbox" aria-label="Edit text" spellCheck={false}
      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.currentTarget.blur(); } }}
      onBlur={(e) => {
        const v = (e.currentTarget.textContent ?? "").trim();
        if (v === textOf(k, x)) return;
        if (!v) { setRev((r) => r + 1); return; }
        patch(x.id, { data: { [TEXT[k]]: v } });
      }}
    >{textOf(k, x)}</span>
  );

  const actions = (k: K, x: AnyItem, extra?: ReactNode, locked = false) => (
    <div className="acts">
      {extra}
      <button className="ibtn" onClick={() => setSrc((x as { src?: string }).src || textOf(k, x))}>Source</button>
      <select className="ibtn" aria-label="Move to another list" value="" disabled={locked}
        onChange={(e) => { const to = e.target.value as K; if (to) patch(x.id, { kind: KIND[to] }, to); }}>
        <option value="">Move…</option>
        {KEYS.filter((z) => z !== k).map((z) => <option key={z} value={z}>{cap(z)}</option>)}
      </select>
      <button className="ibtn" onClick={() => remove(k, x)}>Delete</button>
    </div>
  );

  return (
    <div ref={box}>
      <p className="said" tabIndex={0} aria-label="What you said">
        {at < 0 ? note.transcript : <>{note.transcript.slice(0, at)}<mark>{note.transcript.slice(at, at + q.length)}</mark>{note.transcript.slice(at + q.length)}</>}
      </p>
      <p className="summary" aria-live="polite">{n.tasks} task{n.tasks === 1 ? "" : "s"} · {n.events} event{n.events === 1 ? "" : "s"} · {n.messages} message{n.messages === 1 ? "" : "s"}</p>
      {err && <div className="err" role="alert">{err} {err.includes("connected") && <Link href="/settings">Connect Google</Link>}</div>}
      <div className="tabs" role="tablist">
        {KEYS.map((k) => <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>{cap(k)} {n[k]}</button>)}
      </div>
      <div className="lanes">
        <Lane k="tasks" tab={tab} color="var(--task)" count={n.tasks}>
          {lists.tasks.map((x) => (
            <div className="item" key={`${x.id}-${rev}`}>
              <button role="checkbox" aria-checked={x.done} aria-label="Mark done" className="chk" onClick={() => toggle(x.id, !x.done)} />
              <div className="tx">{editable("tasks", x)}{x.due && <span className="sub">Due {x.due}</span>}{actions("tasks", x)}</div>
            </div>
          ))}
        </Lane>
        <Lane k="events" tab={tab} color="var(--cal)" count={n.events}>
          {lists.events.map((x) => {
            const link = links[x.id] ?? x.google_link, locked = !!link, val = (x.start ?? "").slice(0, 16);
            return (
              <div className="item" key={`${x.id}-${rev}`}>
                <div className="tx">{editable("events", x, locked)}
                  <input className="when" type="datetime-local" aria-label="Event time" defaultValue={val} disabled={locked}
                    onChange={(e) => setTimes((t) => ({ ...t, [x.id]: e.target.value }))}
                    onBlur={(e) => { if (e.target.value && e.target.value !== val) patch(x.id, { data: { start: e.target.value } }); }} />
                  {!x.start && x.when && <span className="sub">Heard “{x.when}”. Set the exact time.</span>}
                  {actions("events", x, link
                    ? <a className="ibtn" href={link} target="_blank" rel="noopener noreferrer">Open in Google Calendar</a>
                    : <button className="ibtn" onClick={() => sync(x.id)}>Add to Google Calendar</button>, locked)}
                </div>
              </div>
            );
          })}
        </Lane>
        <Lane k="messages" tab={tab} color="var(--msg)" count={n.messages}>
          {lists.messages.map((x) => (
            <div className="item draft" key={`${x.id}-${rev}`}>
              <div className="to">{x.to ? `To ${x.to}` : "Recipient not mentioned"}</div>
              <textarea defaultValue={x.body} aria-label="Draft message" id={`m${x.id}`}
                onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== x.body) patch(x.id, { data: { body: v } }); }} />
              {actions("messages", x, <button className="ibtn" onClick={async () => {
                const v = (document.getElementById(`m${x.id}`) as HTMLTextAreaElement).value;
                await navigator.clipboard.writeText(v).catch(() => {}); setCopied(x.id); setTimeout(() => setCopied(0), 1500);
              }}>{copied === x.id ? "Copied" : "Copy"}</button>)}
            </div>
          ))}
        </Lane>
      </div>
      {toast && <div className="toast" role="status">{toast.msg}{toast.undo && <button className="btn" onClick={toast.undo}>Undo</button>}</div>}
    </div>
  );
}

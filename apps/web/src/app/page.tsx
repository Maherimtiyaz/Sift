"use client";
import { useEffect, useRef, useState } from "react";
import Orb, { type OrbMode } from "@/components/Orb";
import Results from "@/components/Results";
import { api, type Note } from "@/lib/api";
import { isMicError, liveSupported, useLiveNote } from "@/lib/useLiveNote";
import { useRecorder } from "@/lib/useRecorder";

type Phase = "idle" | "recording" | "thinking" | "done";
const STAGES = ["Reading your ramble…", "Finding dates and times…", "Drafting your messages…"];
const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export default function Home() {
  const live = useLiveNote(); // streams audio and shows captions while you talk
  const rec = useRecorder(); // fallback: record, then upload when you stop
  const [via, setVia] = useState<"live" | "upload">("upload");
  const [phase, setPhase] = useState<Phase>("idle");
  const [note, setNote] = useState<Note | null>(null);
  const [err, setErr] = useState("");
  const [typed, setTyped] = useState("");
  const [showType, setShowType] = useState(false);
  const [stage, setStage] = useState(0);
  const failed = useRef(false);

  useEffect(() => {
    if (phase !== "thinking") return;
    setStage(0);
    const id = setInterval(() => setStage((s) => Math.min(s + 1, 2)), 1400);
    return () => clearInterval(id);
  }, [phase]);

  function fail(e: unknown) {
    setErr(e instanceof Error ? e.message : "Something went wrong");
    setPhase("idle");
  }

  async function submit(fd: FormData) {
    setPhase("thinking");
    setErr("");
    try {
      fd.set("tz", Intl.DateTimeFormat().resolvedOptions().timeZone);
      setNote(await api.createNote(fd));
      setPhase("done");
      navigator.vibrate?.([12, 40, 12]);
    } catch (e) { fail(e); }
  }

  async function begin() {
    setErr("");
    failed.current = false;
    try {
      if (liveSupported()) {
        try { await live.start(); setVia("live"); setPhase("recording"); return; }
        catch (e) { if (isMicError(e)) throw e; /* socket or worklet trouble: use plain recording */ }
      }
      await rec.start();
      setVia("upload");
      setPhase("recording");
    } catch {
      setErr("The microphone isn’t available. Allow access, or type your note instead.");
      setShowType(true);
    }
  }

  async function finish() {
    if (via === "live") {
      setPhase("thinking");
      setErr("");
      try { setNote(await live.stop()); setPhase("done"); navigator.vibrate?.([12, 40, 12]); }
      catch (e) { fail(e); }
    } else {
      const blob = await rec.stop();
      const fd = new FormData();
      fd.set("audio", blob, "note." + (blob.type.includes("mp4") ? "mp4" : "webm"));
      submit(fd);
    }
  }

  function main() {
    if (phase === "idle") begin();
    else if (phase === "recording") finish();
    else if (phase === "done") { setNote(null); setTyped(""); setPhase("idle"); }
  }

  const mode: OrbMode = phase === "recording" ? "listening" : phase === "thinking" ? "thinking" : "idle";
  const secs = via === "live" ? live.secs : rec.secs;
  const label = { idle: "Tap to record", recording: `Stop · ${clock(secs)}`, thinking: "Sorting…", done: "New note" }[phase];
  const { committed, tail } = live.caption;

  return (
    <main data-phase={phase}>
      <section className="stage">
        <div className="orbwrap">
          <Orb mode={mode} level={via === "live" ? live.level : rec.level} />
          <button className="micHit" onClick={main} disabled={phase === "thinking"} aria-label={phase === "recording" ? "Stop recording" : "Start recording"} />
        </div>
      </section>

      {phase !== "done" && (
        <div className="intro">
          {phase === "idle" && <><h1>Say it messy. Get it sorted.</h1><p>Tap the orb and ramble about your day. Tasks, calendar items and a draft message come out the other side.</p></>}
          {phase === "recording" && (
            <p className="live" aria-label="Live captions">
              {via === "live"
                ? (committed || tail ? <>{committed} <i>{tail}</i></> : <span className="hint">Listening… start talking</span>)
                : <span className="hint">Recording. Tap Stop when you’re done.</span>}
            </p>
          )}
          {phase === "thinking" && <p className="stage-msg" role="status">{STAGES[stage]}</p>}
          {err && <div className="err" role="alert">{err}</div>}
          {phase === "idle" && !showType && <button className="btn" onClick={() => setShowType(true)}>Type instead</button>}
          {phase === "idle" && showType && (
            <div className="typeBox">
              <textarea value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type or paste a messy note…" aria-label="Your note" />
              <button className="btn solid" disabled={!typed.trim()} onClick={() => { const fd = new FormData(); fd.set("text", typed); submit(fd); }}>Sort it out</button>
            </div>
          )}
        </div>
      )}

      {phase === "done" && note && <Results note={note} />}

      <div className="dock"><button className={`dockbtn${phase === "recording" ? " rec" : ""}`} onClick={main} disabled={phase === "thinking"}>{label}</button></div>
    </main>
  );
}

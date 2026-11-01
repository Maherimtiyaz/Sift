"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Note } from "@/lib/api";

export type Caption = { committed: string; tail: string };
export const liveSupported = () =>
  typeof AudioWorkletNode !== "undefined" && typeof WebSocket !== "undefined";
export const isMicError = (e: unknown) =>
  e instanceof DOMException && ["NotAllowedError", "NotFoundError", "SecurityError"].includes(e.name);

type Session = {
  ws?: WebSocket; stream?: MediaStream; ctx?: AudioContext; node?: AudioWorkletNode;
  raf?: number; timer?: number; wake?: WakeLockSentinel | null;
  done?: Note; fail?: Error; settle?: { ok: (n: Note) => void; no: (e: Error) => void };
};

function openSocket(url: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const t = setTimeout(() => { ws.close(); reject(new Error("Live connection timed out")); }, 6000);
    ws.onopen = () => { clearTimeout(t); resolve(ws); };
    ws.onerror = () => { clearTimeout(t); reject(new Error("Couldn’t open the live connection")); };
  });
}

export function useLiveNote() {
  const level = useRef(0);
  const [secs, setSecs] = useState(0);
  const [caption, setCaption] = useState<Caption>({ committed: "", tail: "" });
  const s = useRef<Session>({});

  const teardown = useCallback(() => {
    const x = s.current;
    if (x.raf) cancelAnimationFrame(x.raf);
    if (x.timer) clearInterval(x.timer);
    x.node?.disconnect();
    x.stream?.getTracks().forEach((t) => t.stop());
    x.ctx?.close().catch(() => {});
    x.wake?.release().catch(() => {});
    x.wake = null;
    level.current = 0;
  }, []);
  useEffect(() => () => { teardown(); s.current.ws?.close(); }, [teardown]);

  /** Opens the mic and the socket. Throws if either fails, so the caller can fall back to uploading. */
  const start = useCallback(async () => {
    const x: Session = (s.current = {});
    setCaption({ committed: "", tail: "" });
    x.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    try {
      const { wsUrl } = await api.liveConfig(); // runtime setting, so the same build works against any backend
      if (!wsUrl) throw new Error("Live captions aren’t configured");
      const { ticket } = await api.wsTicket();
      const ws = await openSocket(`${wsUrl}/api/ws/notes?ticket=${encodeURIComponent(ticket)}`);
      x.ws = ws;
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data as string);
        if (m.type === "caption") setCaption({ committed: m.committed, tail: m.tail });
        else if (m.type === "note") { x.done = m.note; x.settle?.ok(m.note); }
        else if (m.type === "error") { x.fail = new Error(m.detail); x.settle?.no(x.fail); }
      };
      ws.onclose = () => {
        if (!x.done && !x.fail) { x.fail = new Error("The live connection dropped. Try again."); x.settle?.no(x.fail); }
      };
      ws.send(JSON.stringify({ type: "start", tz: Intl.DateTimeFormat().resolvedOptions().timeZone }));

      const ctx = new AudioContext();
      x.ctx = ctx;
      await ctx.audioWorklet.addModule("/pcm-worklet.js");
      const src = ctx.createMediaStreamSource(x.stream);
      const an = ctx.createAnalyser();
      an.fftSize = 512;
      src.connect(an);
      const node = new AudioWorkletNode(ctx, "pcm16k");
      x.node = node;
      node.port.onmessage = (e) => { if (ws.readyState === WebSocket.OPEN) ws.send(e.data as ArrayBuffer); };
      const mute = ctx.createGain(); // the worklet only runs while connected to the output, so route it through silence
      mute.gain.value = 0;
      src.connect(node);
      node.connect(mute);
      mute.connect(ctx.destination);

      const buf = new Uint8Array(an.fftSize);
      const loop = () => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) { const d = (v - 128) / 128; sum += d * d; }
        level.current = Math.min(1, Math.sqrt(sum / buf.length) * 5);
        x.raf = requestAnimationFrame(loop);
      };
      loop();
      setSecs(0);
      x.timer = window.setInterval(() => setSecs((n) => n + 1), 1000);
      try { x.wake = await navigator.wakeLock?.request("screen"); } catch { /* optional */ }
      navigator.vibrate?.(18);
    } catch (e) {
      teardown();
      x.ws?.close();
      throw e;
    }
  }, [teardown]);

  /** Flushes the last audio, tells the server to finish, and resolves with the sorted note. */
  const stop = useCallback(async (): Promise<Note> => {
    const x = s.current;
    x.node?.port.postMessage("flush");
    await new Promise((r) => setTimeout(r, 80)); // let the final chunk reach the socket before "stop"
    teardown();
    navigator.vibrate?.(18);
    if (x.done) return x.done;
    if (x.fail) throw x.fail;
    const waiting = new Promise<Note>((ok, no) => {
      x.settle = { ok, no };
      setTimeout(() => no(new Error("Sorting took too long. Try again.")), 90_000);
    });
    x.ws?.send(JSON.stringify({ type: "stop" }));
    try { return await waiting; } finally { x.ws?.close(); }
  }, [teardown]);

  return { level, secs, caption, start, stop };
}

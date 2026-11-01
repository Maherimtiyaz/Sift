"use client";
import { useCallback, useEffect, useRef, useState } from "react";

type Session = {
  mr?: MediaRecorder; stream?: MediaStream; ctx?: AudioContext; raf?: number; timer?: number;
  chunks: Blob[]; wake?: WakeLockSentinel | null;
};

export function useRecorder() {
  const level = useRef(0); // 0..1 mic loudness, read by the orb every frame
  const [secs, setSecs] = useState(0);
  const s = useRef<Session>({ chunks: [] });

  const cleanup = useCallback(() => {
    const x = s.current;
    if (x.raf) cancelAnimationFrame(x.raf);
    if (x.timer) clearInterval(x.timer);
    x.stream?.getTracks().forEach((t) => t.stop());
    x.ctx?.close().catch(() => {});
    x.wake?.release().catch(() => {});
    x.wake = null;
    level.current = 0;
  }, []);
  useEffect(() => cleanup, [cleanup]);

  const start = useCallback(async () => {
    const x = s.current;
    x.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    x.ctx = new AudioContext();
    const an = x.ctx.createAnalyser();
    an.fftSize = 512;
    x.ctx.createMediaStreamSource(x.stream).connect(an);
    const buf = new Uint8Array(an.fftSize);
    const loop = () => {
      an.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) { const d = (v - 128) / 128; sum += d * d; }
      level.current = Math.min(1, Math.sqrt(sum / buf.length) * 5);
      x.raf = requestAnimationFrame(loop);
    };
    loop();
    const type = ["audio/webm;codecs=opus", "audio/mp4"].find((t) => MediaRecorder.isTypeSupported(t));
    x.chunks = [];
    x.mr = new MediaRecorder(x.stream, type ? { mimeType: type } : undefined);
    x.mr.ondataavailable = (e) => { if (e.data.size) x.chunks.push(e.data); };
    x.mr.start(250);
    setSecs(0);
    x.timer = window.setInterval(() => setSecs((n) => n + 1), 1000);
    try { x.wake = await navigator.wakeLock?.request("screen"); } catch { /* optional */ }
    navigator.vibrate?.(18);
  }, []);

  const stop = useCallback(
    () => new Promise<Blob>((resolve) => {
      const x = s.current, mr = x.mr!;
      mr.onstop = () => {
        const blob = new Blob(x.chunks, { type: mr.mimeType });
        cleanup();
        navigator.vibrate?.(18);
        resolve(blob);
      };
      mr.stop();
    }),
    [cleanup],
  );

  return { level, secs, start, stop };
}

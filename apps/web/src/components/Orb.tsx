"use client";
import { useEffect, useRef, type RefObject } from "react";

export type OrbMode = "idle" | "listening" | "thinking";

export default function Orb({ mode, level }: { mode: OrbMode; level: RefObject<number> }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useEffect(() => {
    const cv = ref.current!, ctx = cv.getContext("2d")!;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = cv.height = 360 * dpr;
    ctx.scale(dpr, dpr);
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const read = () => {
      const g = getComputedStyle(document.documentElement);
      return { dark: g.getPropertyValue("--dark").trim() === "1",
               cols: ["--task", "--cal", "--msg"].map((k) => g.getPropertyValue(k).trim()) };
    };
    let C = read(), lv = 0, raf = 0;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onTheme = () => { C = read(); };
    mq.addEventListener("change", onTheme);
    const rgba = (h: string, a: number) => {
      const n = parseInt(h.slice(1, 7), 16);
      return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
    };
    const frame = (ts: number) => {
      const t = ts / 1000, c = 180, m = modeRef.current, k = reduce ? 0.4 : 1;
      lv += ((level.current ?? 0) - lv) * 0.18;
      ctx.clearRect(0, 0, 360, 360);
      const amp = k * (m === "listening" ? 0.05 + lv * 0.3 : m === "thinking" ? 0.13 : 0.05);
      const spd = m === "thinking" ? 2.6 : m === "listening" ? 1.3 : 0.5;
      ctx.globalCompositeOperation = C.dark ? "lighter" : "source-over";
      for (let i = 0; i < 3; i++) {
        ctx.beginPath();
        const base = 96 + i * 7 + (m === "listening" ? lv * 30 : 0);
        for (let j = 0; j <= 96; j++) {
          const a = (j / 96) * Math.PI * 2;
          const n = Math.sin(a * 2 + t * spd + i * 2) * 0.5 + Math.sin(a * 3 - t * spd * 1.3 + i) * 0.35
                  + Math.sin(a * 5 + t * spd * 0.7 - i * 3) * 0.15;
          const r = base * (1 + amp * n * 2.2), x = c + Math.cos(a) * r, y = c + Math.sin(a) * r;
          if (j) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        }
        ctx.closePath();
        const ox = Math.cos(t * 0.6 + i * 2.1) * 22, oy = Math.sin(t * 0.5 + i * 2.1) * 22;
        const g = ctx.createRadialGradient(c + ox, c + oy, 8, c, c, 135);
        g.addColorStop(0, rgba(C.cols[i], C.dark ? 0.6 : 0.75));
        g.addColorStop(1, rgba(C.cols[i], 0));
        ctx.fillStyle = g;
        ctx.fill();
      }
      ctx.globalCompositeOperation = "source-over";
      if (m === "listening" && !reduce) {
        for (let r = 0; r < 3; r++) {
          const p = (t * 0.45 + r / 3) % 1;
          ctx.beginPath();
          ctx.arc(c, c, 104 + p * 76, 0, Math.PI * 2);
          ctx.strokeStyle = rgba(C.cols[r], (1 - p) * 0.4);
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); mq.removeEventListener("change", onTheme); };
  }, [level]);

  return <canvas ref={ref} aria-hidden="true" style={{ width: "100%", height: "100%" }} />;
}

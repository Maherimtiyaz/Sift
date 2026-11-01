"use client";
import { useState, type FormEvent } from "react";

export default function AuthForm({ initialMode }: { initialMode: "login" | "register" }) {
  const [mode, setMode] = useState(initialMode);
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function go(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const res = await fetch(`/api/auth/${mode}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password: pw }),
        signal: AbortSignal.timeout(20_000),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        location.href = "/";
        return;
      }
      setErr(typeof body.detail === "string" ? body.detail : "We couldn’t complete that request. Please try again.");
    } catch (error) {
      setErr(error instanceof DOMException && error.name === "TimeoutError"
        ? "That took too long. Please try again."
        : "We couldn’t reach Sift. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page auth">
      <h1 className="h1s">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
      <form className="lane on" onSubmit={go}>
        <label htmlFor="email">Email</label>
        <input id="email" className="field" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="pw">Password</label>
        <input id="pw" className="field" type="password" required minLength={mode === "register" ? 10 : undefined}
          autoComplete={mode === "login" ? "current-password" : "new-password"} value={pw} onChange={(e) => setPw(e.target.value)} />
        {mode === "register" && <p className="sub">Use at least 10 characters.</p>}
        {err && <div className="err" role="alert">{err}</div>}
        <button className="btn solid" disabled={busy}>{busy ? "One moment…" : mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="linkbtn" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(""); }}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}

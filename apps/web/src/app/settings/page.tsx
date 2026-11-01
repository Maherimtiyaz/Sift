"use client";
import { useEffect, useState, type CSSProperties } from "react";
import { api } from "@/lib/api";

const MSG: Record<string, string> = {
  connected: "Google Calendar connected.",
  denied: "Google sign-in was cancelled.",
  missing_scope: "Calendar permission was unticked. Connect again and keep it ticked.",
  no_refresh: "Google didn’t return a long-lived token. Remove Sift at myaccount.google.com/permissions, then connect again.",
};

export default function Settings() {
  const [st, setSt] = useState<{ connected: boolean; email: string | null } | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    setNote(MSG[new URLSearchParams(location.search).get("google") ?? ""] ?? "");
    api.googleStatus().then(setSt).catch((e: Error) => setErr(e.message));
  }, []);

  return (
    <main className="page">
      <h1 className="h1s">Settings</h1>
      {note && <p className="summary" role="status">{note}</p>}
      {err && <div className="err" role="alert">{err}</div>}
      <section className="lane on" style={{ maxWidth: 520 }}>
        <div className="lh"><span className="dot" style={{ "--a": "var(--cal)" } as CSSProperties} /><h2>Google Calendar</h2></div>
        {st?.connected ? (
          <>
            <p>Connected as <strong>{st.email ?? "your Google account"}</strong>. Events from your notes can be added with one tap.</p>
            <button className="btn" onClick={async () => { await api.googleDisconnect(); setSt({ connected: false, email: null }); }}>Disconnect</button>
          </>
        ) : (
          <>
            <p>Connect once and Sift can put events from your voice notes straight into your calendar. It can only create and edit events.</p>
            <button className="btn solid" onClick={async () => { const { url } = await api.googleConnect(); location.href = url; }}>Connect Google Calendar</button>
          </>
        )}
      </section>
    </main>
  );
}

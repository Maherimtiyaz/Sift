"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function DemoModeNotice() {
  const [status, setStatus] = useState<"loading" | "demo" | "ready" | "error">("loading");

  useEffect(() => {
    api.liveConfig()
      .then(({ demoMode }) => setStatus(demoMode ? "demo" : "ready"))
      .catch(() => setStatus("error"));
  }, []);

  if (status === "demo") {
    return (
      <p className="demo-mode" role="status">
        DEMO MODE · Fixed sample output; your input isn’t sent to an AI provider.
      </p>
    );
  }
  if (status === "error") {
    return <p className="provider-status" role="status">AI mode unavailable. Check the API connection.</p>;
  }
  return null;
}

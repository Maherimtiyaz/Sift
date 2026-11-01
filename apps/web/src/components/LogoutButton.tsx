"use client";

export default function LogoutButton() {
  return (
    <button className="linkbtn" onClick={async () => { await fetch("/api/auth/logout", { method: "POST" }); location.href = "/login"; }}>
      Log out
    </button>
  );
}

"use client";

import { useState } from "react";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user, pass }),
      });
      if (res.ok) {
        window.location.href = "/";
        return;
      }
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "Bejelentkezés sikertelen");
    } catch {
      setError("Hálózati hiba");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        background: "#060d1a",
        color: "#a0b0ff",
        fontFamily: "sans-serif",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        margin: 0,
      }}
    >
      <form
        onSubmit={onSubmit}
        style={{
          background: "#0b1424",
          border: "1px solid #1c2c4a",
          borderRadius: 12,
          padding: 32,
          width: "min(360px, 90vw)",
          display: "flex",
          flexDirection: "column",
          gap: 16,
          boxShadow: "0 10px 40px rgba(0,0,0,0.5)",
        }}
      >
        <h1 style={{ fontSize: "1.4rem", color: "#fff", margin: 0, textAlign: "center" }}>
          🔒 Bejelentkezés
        </h1>

        <input
          type="text"
          placeholder="Felhasználónév"
          value={user}
          onChange={(e) => setUser(e.target.value)}
          autoComplete="username"
          autoFocus
          style={inputStyle}
        />
        <input
          type="password"
          placeholder="Jelszó"
          value={pass}
          onChange={(e) => setPass(e.target.value)}
          autoComplete="current-password"
          style={inputStyle}
        />

        {error ? (
          <div style={{ color: "#ff6b6b", fontSize: "0.85rem", textAlign: "center" }}>
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={loading}
          style={{
            background: loading ? "#2a3a5a" : "#3b82f6",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "12px",
            fontSize: "1rem",
            cursor: loading ? "default" : "pointer",
            fontWeight: 600,
          }}
        >
          {loading ? "..." : "Belépés"}
        </button>
      </form>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  background: "#060d1a",
  border: "1px solid #1c2c4a",
  borderRadius: 8,
  padding: "12px",
  color: "#e0e6ff",
  fontSize: "1rem",
  outline: "none",
};

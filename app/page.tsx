import Script from "next/script";
import { LEGACY_BODY } from "./legacyBody";
import { MAINTENANCE } from "@/lib/config";

export const dynamic = "force-dynamic";

export default function Page() {
  if (MAINTENANCE) {
    return (
      <div
        style={{
          background: "#060d1a",
          color: "#a0b0ff",
          fontFamily: "sans-serif",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          margin: 0,
          flexDirection: "column",
          gap: 16,
        }}
      >
        <h1 style={{ fontSize: "2rem", color: "#fff", margin: 0 }}>
          🔧 Karbantartás alatt
        </h1>
        <p style={{ color: "#555", margin: 0 }}>Hamarosan visszatérünk.</p>
      </div>
    );
  }

  return (
    <>
      <div dangerouslySetInnerHTML={{ __html: LEGACY_BODY }} />
      <Script src="/legacy.js" strategy="afterInteractive" />
    </>
  );
}

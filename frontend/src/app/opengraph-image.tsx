import { ImageResponse } from "next/og";

// The preview picture shown when the link is shared (LinkedIn, Upwork, chat apps). Drawn at build time.
export const alt = "AnswerTrail: support answers you can trace to the source";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "70px 80px",
          color: "#ffffff",
          background: "linear-gradient(135deg, #0f766e 0%, #0c3b37 100%)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <svg width="64" height="64" viewBox="0 0 32 32">
            <rect width="32" height="32" rx="8" fill="rgba(255,255,255,0.18)" />
            <path d="M9 22 15 14 23 10" stroke="#fff" strokeWidth="2" strokeLinecap="round" fill="none" opacity="0.6" />
            <circle cx="9" cy="22" r="2.6" fill="#fff" />
            <circle cx="15" cy="14" r="2.6" fill="#fff" />
            <circle cx="23" cy="10" r="3.2" fill="#fff" />
          </svg>
          <div style={{ display: "flex", fontSize: 44, fontWeight: 800, letterSpacing: -1 }}>
            Answer<span style={{ color: "#86dbd0" }}>Trail</span>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <div style={{ fontSize: 76, fontWeight: 800, lineHeight: 1.05, letterSpacing: -2, maxWidth: 980 }}>
            Support answers you can trace to the source.
          </div>
          <div style={{ fontSize: 30, color: "#cfeae5", maxWidth: 940 }}>
            A RAG support assistant that cites its sources, says &ldquo;I don&apos;t know&rdquo; instead of guessing, and
            publishes its own evaluation.
          </div>
        </div>

        <div style={{ display: "flex", gap: 14, fontSize: 24, color: "#86dbd0" }}>
          <span>Cited answers</span>
          <span>·</span>
          <span>Honest refusals</span>
          <span>·</span>
          <span>Measured results</span>
        </div>
      </div>
    ),
    size,
  );
}

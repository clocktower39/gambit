// Stable, submittable demo-video URL: https://gambit.nudepineapple.com/video
// Submit this link now; to fill it in, either set NEXT_PUBLIC_VIDEO_URL to a hosted URL
// (YouTube/Vimeo/Loom/etc.) OR drop the file at frontend/public/gambit-demo.mp4.
// Until one of those exists it shows a "coming soon" placeholder; once present it embeds
// the player (URL → iframe, self-hosted .mp4 → native <video>) inline.

import type { Metadata } from "next";
import { existsSync } from "node:fs";
import { join } from "node:path";

// ── Where the video comes from, in priority order ─────────────────────────────────────
//  1. NEXT_PUBLIC_VIDEO_URL env var (YouTube/Vimeo/Loom/any URL), OR
//  2. drop a file at frontend/public/gambit-demo.mp4 — it's served at /gambit-demo.mp4.
// Whichever exists wins; if neither, the "coming soon" placeholder shows.
const SELF_HOSTED = "/gambit-demo.mp4";
const VIDEO_URL = process.env.NEXT_PUBLIC_VIDEO_URL ?? "";

export const metadata: Metadata = {
  title: "Gambit — demo video",
  description: "Watch Gambit, the self-improving auto-negotiator, climb.",
};

// Turn a YouTube / Vimeo / Loom share link into its embeddable form. Anything else
// (including a direct .mp4) returns null → rendered with a native <video> tag.
function toEmbed(url: string): string | null {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");
    if (host === "youtu.be") return `https://www.youtube.com/embed/${u.pathname.slice(1)}`;
    if (host.endsWith("youtube.com")) {
      const id = u.searchParams.get("v");
      if (id) return `https://www.youtube.com/embed/${id}`;
      if (u.pathname.startsWith("/embed/")) return url;
    }
    if (host.endsWith("vimeo.com")) return `https://player.vimeo.com/video/${u.pathname.split("/").filter(Boolean).pop()}`;
    if (host.endsWith("loom.com")) return url.replace("/share/", "/embed/");
  } catch {
    /* fall through */
  }
  return null;
}

export default function VideoPage() {
  // Prefer the env-var URL; otherwise use the self-hosted file if it's actually present.
  const selfHosted = existsSync(join(process.cwd(), "public", SELF_HOSTED));
  const src = VIDEO_URL.trim() || (selfHosted ? SELF_HOSTED : "");
  const ready = src.length > 0;
  const embed = ready ? toEmbed(src) : null;

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.5rem",
        padding: "2rem",
        fontFamily: "var(--font-sans)",
        background: "#0b0b0f",
        color: "#e8e8ee",
      }}
    >
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "clamp(2rem, 5vw, 3.25rem)",
          fontWeight: 600,
          margin: 0,
          letterSpacing: "-0.02em",
        }}
      >
        Gambit
      </h1>
      <p style={{ margin: 0, opacity: 0.7, fontSize: "1.05rem", textAlign: "center", maxWidth: "32rem" }}>
        A self-improving auto-negotiator that teaches itself to haggle.
      </p>

      <div
        style={{
          width: "min(960px, 100%)",
          aspectRatio: "16 / 9",
          borderRadius: "14px",
          overflow: "hidden",
          background: "#15151c",
          border: "1px solid #26262f",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {ready ? (
          embed ? (
            <iframe
              src={embed}
              title="Gambit demo video"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
              allowFullScreen
              style={{ width: "100%", height: "100%", border: 0 }}
            />
          ) : (
            <video src={src} controls playsInline style={{ width: "100%", height: "100%" }} />
          )
        ) : (
          <div style={{ textAlign: "center", padding: "2rem", opacity: 0.75 }}>
            <div style={{ fontSize: "1.4rem", fontWeight: 600, marginBottom: "0.5rem" }}>Demo video coming soon</div>
            <div style={{ fontSize: "0.95rem", opacity: 0.7 }}>Check back shortly — the render is on its way.</div>
          </div>
        )}
      </div>

      <a
        href="/live"
        style={{
          color: "#a6a6ff",
          textDecoration: "none",
          fontSize: "0.95rem",
          fontFamily: "var(--font-mono)",
        }}
      >
        → watch it climb live
      </a>
    </main>
  );
}

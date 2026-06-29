"use client";

// Voice seat for the /chat page. The browser is the BUYER; you speak, and the trained M3 seller
// (gambit/voice/seller_worker.py) talks back. LiveKit moves the audio; Gemini is the ears/mouth;
// the negotiating brain is the same MiniMax-M3 policy the typed chat faces.
//
// Flow: POST {BACKEND}/voice-token → { serverUrl, token, room } → <LiveKitRoom> connects the mic and
// plays the seller's TTS. The running voice worker auto-dispatches into the room as the seller.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  TrackToggle,
  useRoomContext,
  useVoiceAssistant,
} from "@livekit/components-react";
import { RoomEvent, Track, type Participant, type TranscriptionSegment } from "livekit-client";
import "@livekit/components-styles";

const BACKEND = process.env.NEXT_PUBLIC_AGUI_HTTP ?? "http://localhost:8000";

type Conn = { serverUrl: string; token: string; room: string };
type Status = "idle" | "connecting" | "live" | "error";

export default function VoiceConsole() {
  const [conn, setConn] = useState<Conn | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    setStatus("connecting");
    setError(null);
    try {
      const r = await fetch(`${BACKEND}/voice-token`, { method: "POST" });
      const j = await r.json().catch(() => ({ error: "bad response" }));
      if (!r.ok) {
        // 503 → voice not configured/installed; surface the backend's hint, then fall back to typing.
        setError(j.detail || j.error || `error ${r.status}`);
        setStatus("error");
        return;
      }
      setConn({ serverUrl: j.serverUrl, token: j.token, room: j.room });
      setStatus("live");
    } catch {
      setError("Can't reach the backend — is the AG-UI server running?");
      setStatus("error");
    }
  }, []);

  const stop = useCallback(() => {
    setConn(null);
    setStatus("idle");
  }, []);

  if (!conn) {
    return (
      <div className="voiceBar">
        <button className="voiceStart" onClick={start} disabled={status === "connecting"}>
          <MicGlyph />
          {status === "connecting" ? "Connecting…" : "Talk to the seller"}
        </button>
        <span className="voiceHint">
          {status === "error" ? <span className="voiceErr">{error}</span>
            : "Speak your offer out loud — the trained seller hears you and talks back."}
        </span>
      </div>
    );
  }

  return (
    <LiveKitRoom
      serverUrl={conn.serverUrl}
      token={conn.token}
      connect
      audio
      video={false}
      onDisconnected={stop}
      className="voiceRoom"
    >
      <RoomAudioRenderer />
      <VoiceLive onHangup={stop} />
    </LiveKitRoom>
  );
}

const STATE_LABEL: Record<string, string> = {
  connecting: "Connecting…",
  initializing: "Waking the seller…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Seller is talking",
};

function VoiceLive({ onHangup }: { onHangup: () => void }) {
  const { state, audioTrack } = useVoiceAssistant();
  const transcript = useTranscript();

  return (
    <div className="voiceLive">
      <div className="voiceStatusRow">
        <span className={`voiceState s-${state}`}>{STATE_LABEL[state] ?? "Live"}</span>
        <BarVisualizer state={state} trackRef={audioTrack} barCount={5} className="voiceViz" />
        <div className="voiceCtrls">
          <TrackToggle source={Track.Source.Microphone} className="voiceMic" showIcon>
            Mic
          </TrackToggle>
          <button className="voiceHang" onClick={onHangup}>End call</button>
        </div>
      </div>
      {transcript.length > 0 && (
        <div className="voiceTranscript" aria-live="polite">
          {transcript.map((t) => (
            <div key={t.id} className={`vt ${t.who}`}>
              <span className="vtwho">{t.who === "you" ? "You" : "Seller"}</span>
              <span className="vttext">{t.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

type Line = { id: string; who: "you" | "seller"; text: string };

// Live transcript from LiveKit transcription segments — your STT and the seller's spoken words,
// labelled by who's local. Best-effort: if the transport doesn't emit segments, voice still works;
// only this panel stays empty.
function useTranscript(): Line[] {
  const room = useRoomContext();
  const [lines, setLines] = useState<Line[]>([]);
  const byId = useRef<Map<string, Line>>(new Map());

  useEffect(() => {
    if (!room) return;
    const onSeg = (segments: TranscriptionSegment[], participant?: Participant) => {
      const who: Line["who"] = participant?.isLocal ? "you" : "seller";
      for (const s of segments) {
        if (s.text?.trim()) byId.current.set(s.id, { id: s.id, who, text: s.text });
      }
      setLines(Array.from(byId.current.values()).slice(-8)); // keep the last few exchanges
    };
    room.on(RoomEvent.TranscriptionReceived, onSeg);
    return () => {
      room.off(RoomEvent.TranscriptionReceived, onSeg);
    };
  }, [room]);

  return lines;
}

function MicGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 17v4" />
    </svg>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ThemeToggle from "./ThemeToggle";

const BACKEND = process.env.NEXT_PUBLIC_AGUI_HTTP ?? "http://localhost:8000";

/* ---------- types: the exact shapes the backend serves ---------- */
type Run = {
  run_id: string; ts: string; category: string; source: string | null; title: string;
  checkpoint: string | null; episodes: number; deals: number; mean_reward: number | null;
  viol: number; buckets: string[];
};
type Move = { role: "seller" | "buyer"; action?: string | null; offer: number | null; text: string; ts?: string | null };
type Outcome = { result: string; deal: boolean; price: number | null; reward: number | null; surplus: number | null; skill: number | null; viol: number; turns: number | null; bucket: string | null; gen: number | null };
type Reflection = { bucket: string | null; seller_lesson: string | null; buyer_lesson: string | null; surplus: number | null; viol: number };
type CurvePt = { gen: number; reward: number | null; skill?: number | null; viol?: number; promoted?: boolean };
type Sample = { bucket: string | null; reward: number | null; skill: number | null; transcript: string; gen?: number | null; item?: string | null; persona?: string | null; seed?: number | null };
type RunEvent = { kind: string; gen: number | null; bucket: string | null; verdict: string | null; delta: number | null; msg: string | null };
type PanelScore = { n?: number | null; reward: number | null; skill: number | null; viol: number; buckets?: Record<string, number> };
type Transfer = { locked_start: PanelScore; locked_final: PanelScore; locked_delta: number | null; transfer_ok?: boolean | null };
type Detail = {
  run_id: string; title: string | null; moves: Move[]; outcomes: Outcome[]; reflections: Reflection[];
  curve: CurvePt[]; samples?: Sample[]; events?: RunEvent[]; transfer?: Transfer | null;
  generations?: number; spans?: number; error?: string; retry?: boolean; updated_ts?: string | null;
};
type ViewMode = "live" | "history";
type LoadStatus = "idle" | "loading" | "throttled" | "timeout" | "error" | "offline";
type LiveSnapshot = {
  run: Run | null;
  detail: Detail | null;
  connected: boolean;
  waiting: boolean;
  done: boolean;
  error: string | null;
};

/* ---------- formatting ---------- */
const money = (v: number | null | undefined) => (v == null ? "—" : `$${Number.isInteger(v) ? v : v.toFixed(2)}`);
const num2 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
const signed = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;

const CAT_COLORS: Record<string, string> = {
  "self-play": "#6ea8ff", "offline-rl": "#4fd1a8", "human-vs-agent": "#e0a85a",
  reflection: "#9b8cff", negotiation: "#869c8b", harvest: "#e08a5b", overview: "#8b97a8", eval: "#9b8cff",
};
const catColor = (c: string) => CAT_COLORS[c] ?? "#8a909c";
const fmt = (ts: string) => { try { return new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); } catch { return ts; } };
const mclock = (ts?: string | null) => { if (!ts) return ""; try { return new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }); } catch { return ""; } };
const ageMs = (ts: string) => { const t = Date.parse(ts); return Number.isNaN(t) ? Infinity : Date.now() - t; };
const relAge = (ts: string) => {
  const m = ageMs(ts); if (!Number.isFinite(m)) return "";
  const s = Math.round(m / 1000);
  if (s < 60) return `${s}s ago`;
  const min = Math.round(s / 60); if (min < 60) return `${min}m ago`;
  const h = Math.round(min / 60); if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
};

const TIPS: Record<string, string> = {
  "self-play": "A local training run scored against deterministic and held-out buyer panels.",
  "offline-rl": "Learning from a fixed batch of past matches — no live play, no human eyes.",
  "human-vs-agent": "A real person haggled against the trained seller.",
  skill: "Share of the available surplus the agent captured (0–1).",
  reward: "Held-out score the agent is optimized for (0–1).",
  viol: "Times a hard negotiation rule was broken. Zero is clean.",
  bucket: "The difficulty band of the counterparty (e.g. low/mid/high).",
  promotion: "A Gemini-written lesson that raised held-out reward, so it was kept.",
  rejection: "A proposed lesson that did not help, so it was discarded.",
};
const Tip = ({ k, children }: { k: string; children: React.ReactNode }) => (
  <span className="tip" tabIndex={0} aria-label={TIPS[k]}>{children}<span className="tipbox" role="tooltip">{TIPS[k]}</span></span>
);

/* integrity (viol) signal — clean vs broken-rule, honest about blind checks */
function Viol({ n, blind }: { n: number; blind?: boolean }) {
  return <span className={`viol ${n === 0 ? "clean" : "bad"}`}>{n === 0 ? (blind ? "viol 0" : "clean") : `${n} viol`}</span>;
}

/* parse a league sample transcript ("SELLER [$725]: …") into addressable moves */
function parseTranscript(t: string): Move[] {
  const out: Move[] = [];
  for (const raw of t.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/^(SELLER|BUYER)(?:\s*\[\$([\d.]+)\])?:\s*(.*)$/i);
    if (m) {
      out.push({ role: m[1].toLowerCase() === "seller" ? "seller" : "buyer", offer: m[2] ? Number(m[2]) : null, text: m[3] });
    } else if (out.length) {
      out[out.length - 1].text += " " + line;
    }
  }
  return out;
}

const blankLive: LiveSnapshot = { run: null, detail: null, connected: false, waiting: false, done: false, error: null };

const asNum = (v: unknown): number | null => {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
};

const asInt = (v: unknown): number | null => {
  const n = asNum(v);
  return n == null ? null : Math.trunc(n);
};

const eventTime = (ts: unknown): string => {
  if (typeof ts === "number" && Number.isFinite(ts)) return new Date(ts * 1000).toISOString();
  if (typeof ts === "string" && ts) return ts;
  return new Date().toISOString();
};

const emptyDetail = (runId: string, ts?: string): Detail => ({
  run_id: runId,
  title: "Local training run",
  moves: [],
  outcomes: [],
  reflections: [],
  curve: [],
  samples: [],
  events: [],
  transfer: null,
  spans: 0,
  updated_ts: ts ?? new Date().toISOString(),
});

const panelScore = (raw: any): PanelScore => ({
  n: asInt(raw?.n),
  reward: asNum(raw?.reward),
  skill: asNum(raw?.skill),
  viol: asInt(raw?.viol) ?? 0,
  buckets: raw?.buckets && typeof raw.buckets === "object" ? raw.buckets : undefined,
});

const movesToTranscript = (moves: Move[]): string =>
  moves.map((m) => {
    const offer = m.offer == null ? "" : ` [${money(m.offer)}]`;
    return `${m.role.toUpperCase()}${offer}: ${m.text || m.action || ""}`.trim();
  }).join("\n");

const replaceCurvePoint = (curve: CurvePt[], pt: CurvePt) => {
  const next = curve.filter((p) => p.gen !== pt.gen);
  next.push(pt);
  return next.sort((a, b) => a.gen - b.gen);
};

const liveRunFromDetail = (detail: Detail, previous: Run | null, ts: string, done: boolean): Run => {
  const curve = detail.curve;
  const lastReward = [...curve].reverse().find((p) => p.reward != null)?.reward ?? null;
  const buckets = Array.from(new Set([
    ...detail.outcomes.map((o) => o.bucket).filter(Boolean),
    ...(detail.samples ?? []).map((s) => s.bucket).filter(Boolean),
    ...Object.keys(detail.transfer?.locked_final.buckets ?? {}),
  ])) as string[];
  const deals = detail.outcomes.filter((o) => o.deal).length;
  const violFromCurve = curve.reduce((sum, p) => sum + (p.viol ?? 0), 0);
  const violFromOutcomes = detail.outcomes.reduce((sum, o) => sum + (o.viol ?? 0), 0);
  return {
    run_id: detail.run_id,
    ts,
    category: "self-play",
    source: "agent",
    title: detail.title ?? previous?.title ?? "Local training run",
    checkpoint: done ? "complete" : "watch",
    episodes: detail.outcomes.length,
    deals,
    mean_reward: lastReward,
    viol: violFromCurve || violFromOutcomes,
    buckets,
  };
};

const applyWatchEvent = (state: LiveSnapshot, ev: any): LiveSnapshot => {
  const ts = eventTime(ev?.ts);
  if (ev?.type === "waiting") {
    return { ...state, connected: true, waiting: true, error: null };
  }
  if (ev?.type === "run") {
    const runId = String(ev.run_id || "latest");
    const detail = emptyDetail(runId, ts);
    return {
      run: liveRunFromDetail(detail, null, ts, false),
      detail,
      connected: true,
      waiting: false,
      done: false,
      error: null,
    };
  }

  const runId = state.detail?.run_id ?? state.run?.run_id ?? "latest";
  const current: Detail = {
    ...emptyDetail(runId, ts),
    ...(state.detail ?? {}),
    updated_ts: ts,
    spans: (state.detail?.spans ?? 0) + 1,
  };

  let detail = current;
  let done = state.done;

  if (ev?.type === "start") {
    const title = `${ev.train_family ?? "training"} -> ${ev.locked_family ?? "locked"} transfer`;
    detail = { ...current, title };
  } else if (ev?.type === "gen") {
    const gen = asInt(ev.gen);
    if (gen != null) {
      detail = {
        ...current,
        curve: replaceCurvePoint(current.curve, {
          gen,
          reward: asNum(ev.reward),
          skill: asNum(ev.skill),
          viol: asInt(ev.viol) ?? 0,
          promoted: Boolean(ev.improved),
        }),
        generations: Math.max(current.generations ?? 0, gen + 1),
      };
    }
  } else if (ev?.type === "episode") {
    const moves = Array.isArray(ev.moves) ? ev.moves.map((m: any) => ({
      role: m.role === "buyer" ? "buyer" : "seller",
      action: m.action ?? null,
      offer: asNum(m.offer),
      text: String(m.text ?? ""),
    })) : [];
    const rawOutcome = ev.outcome ?? {};
    const outcome: Outcome = {
      result: String(rawOutcome.reason ?? (rawOutcome.deal ? "deal" : "no deal")),
      deal: Boolean(rawOutcome.deal),
      price: asNum(rawOutcome.price),
      reward: asNum(rawOutcome.reward),
      surplus: asNum(rawOutcome.surplus),
      skill: asNum(rawOutcome.skill),
      viol: asInt(rawOutcome.viol) ?? 0,
      turns: asInt(rawOutcome.turns),
      bucket: ev.bucket ?? null,
      gen: asInt(ev.gen),
    };
    const sample: Sample = {
      bucket: ev.bucket ?? null,
      reward: outcome.reward,
      skill: outcome.skill,
      transcript: movesToTranscript(moves),
      gen: outcome.gen,
      item: ev.item ?? null,
      persona: ev.persona ?? null,
      seed: asInt(ev.seed),
    };
    detail = {
      ...current,
      outcomes: [...current.outcomes, outcome],
      samples: [...(current.samples ?? []), sample],
    };
  } else if (ev?.type === "transfer") {
    detail = {
      ...current,
      transfer: {
        locked_start: panelScore(ev.locked_start),
        locked_final: panelScore(ev.locked_final),
        locked_delta: asNum(ev.locked_delta),
        transfer_ok: null,
      },
    };
  } else if (ev?.type === "done") {
    done = true;
    detail = {
      ...current,
      transfer: current.transfer ? { ...current.transfer, transfer_ok: Boolean(ev.transfer_ok) } : current.transfer,
    };
  }

  return {
    ...state,
    run: liveRunFromDetail(detail, state.run, ts, done),
    detail,
    connected: true,
    waiting: false,
    done,
    error: null,
  };
};

/* =====================================================================
   THE CLIMB — the hero. Held-out reward (and skill) by generation.
   Anchored 0–1. Promotions marked. Degrades gracefully at one point.
   ===================================================================== */
export function Climb({ curve, live }: { curve: CurvePt[]; live: boolean }) {
  const rPts = curve.filter((p) => p.reward != null);
  const sPts = curve.filter((p) => p.skill != null);
  const W = 1000, H = 340, padL = 46, padR = 22, padT = 26, padB = 34;
  const maxG = Math.max(1, ...curve.map((p) => p.gen));
  const x = (g: number) => padL + (g / maxG) * (W - padL - padR);
  const y = (v: number) => H - padB - Math.max(0, Math.min(1, v)) * (H - padT - padB);

  const path = (pts: { gen: number; reward?: number | null; skill?: number | null }[], key: "reward" | "skill") =>
    pts.map((p, i) => `${i ? "L" : "M"}${x(p.gen).toFixed(1)},${y((p[key] as number)).toFixed(1)}`).join(" ");
  const rewardLine = path(rPts, "reward");
  const skillLine = path(sPts as any, "skill");
  const baseY = y(0).toFixed(1);
  const area = rPts.length > 1 ? `${rewardLine} L${x(rPts[rPts.length - 1].gen).toFixed(1)},${baseY} L${x(rPts[0].gen).toFixed(1)},${baseY} Z` : "";

  const warming = rPts.length === 0;          // held-out reward not in yet
  const single = rPts.length === 1;
  const showDots = rPts.length <= 40;
  const last = rPts[rPts.length - 1];

  return (
    <div className="climb">
      <svg viewBox={`0 0 ${W} ${H}`} className="climbSvg" role="img"
        aria-label="Held-out reward by generation, anchored 0 to 1">
        <defs>
          <linearGradient id="rfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#d9a24a" stopOpacity="0.34" />
            <stop offset="100%" stopColor="#d9a24a" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={padL} y1={y(v)} x2={W - padR} y2={y(v)} className={`cgrid ${v === 0 ? "base" : ""}`} />
            <text x={padL - 9} y={y(v) + 3.5} textAnchor="end" className="caxis">{v}</text>
          </g>
        ))}
        {/* gen ticks along the base */}
        {curve.length > 1 && curve.map((p) => (
          <text key={p.gen} x={x(p.gen)} y={H - padB + 16} textAnchor="middle" className="cgen">{p.gen}</text>
        ))}
        {area && <path d={area} className="cArea" />}
        {skillLine && <path d={skillLine} className="cSkill" fill="none" />}
        {rewardLine && <path d={rewardLine} className="cReward" fill="none" pathLength={1} />}
        {/* promotion markers — where a kept lesson lifted the curve */}
        {showDots && rPts.filter((p) => p.promoted).map((p) => (
          <g key={`pr${p.gen}`} transform={`translate(${x(p.gen)},${y(p.reward as number)})`}>
            <path d="M0,-7 L6,0 L0,7 L-6,0 Z" className="cPromo" />
          </g>
        ))}
        {showDots && rPts.map((p, i) => (
          <circle key={p.gen} cx={x(p.gen)} cy={y(p.reward as number)} r={i === rPts.length - 1 ? 5 : 3.2}
            className={`cDot ${i === rPts.length - 1 ? "last" : ""} ${p.promoted ? "promoted" : ""}`} />
        ))}
        {live && last && (
          <circle cx={x(last.gen)} cy={y(last.reward as number)} r="5" className="cPulse" />
        )}
        {warming && (
          <text x={(W) / 2} y={H / 2} textAnchor="middle" className="cWarm">held-out reward lands as the league plays</text>
        )}
      </svg>

      <div className="climbFoot">
        <span className="legend"><i className="sw reward" />held-out reward</span>
        {sPts.length > 0 && <span className="legend"><i className="sw skill" />skill</span>}
        <span className="legend"><i className="sw promo" />lesson kept</span>
        {single && <span className="climbNote">gen 0 · the curve grows as it runs</span>}
        {warming && <span className="climbNote">reward pending · only skill has reported</span>}
      </div>

      {/* a11y / honesty: the same numbers as a table */}
      <details className="dataTable">
        <summary>Curve as a table</summary>
        <table>
          <thead><tr><th>gen</th><th>reward</th><th>skill</th><th>lesson</th></tr></thead>
          <tbody>
            {curve.map((p) => (
              <tr key={p.gen}><td>{p.gen}</td><td>{num2(p.reward)}</td><td>{num2(p.skill)}</td><td>{p.promoted ? "kept" : "—"}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

/* the climb's vitals — honest about N=1 */
export function Vitals({ curve, run }: { curve: CurvePt[]; run?: Run }) {
  const rPts = curve.filter((p) => p.reward != null);
  const gens = curve.length;
  const cur = rPts.length ? (rPts[rPts.length - 1].reward as number) : null;
  const base = rPts.length ? (rPts[0].reward as number) : null;
  const best = rPts.length ? Math.max(...rPts.map((p) => p.reward as number)) : null;
  const delta = cur != null && base != null ? cur - base : null;
  const promotions = curve.filter((p) => p.promoted).length;
  const totViol = curve.reduce((s, p) => s + (p.viol || 0), 0);

  return (
    <div className="vitals">
      <div className="vt">
        <span className="vk">{gens > 1 ? "Generations" : "Generation"}</span>
        <span className="vv">{gens > 1 ? gens : "0"}</span>
        <span className="vsub">{gens > 1 ? "held-out evals" : "single eval so far"}</span>
      </div>
      <div className="vt">
        <span className="vk">{rPts.length > 1 ? "Reward now" : "Reward (gen 0)"}</span>
        <span className="vv brass">{cur == null ? "—" : cur.toFixed(2)}</span>
        <span className="vsub">{delta == null ? "baseline · 1 eval" : <>from {base!.toFixed(2)} · <b className={delta < 0 ? "down" : "up"}>{signed(delta)}</b></>}</span>
      </div>
      <div className="vt">
        <span className="vk">Best held-out</span>
        <span className="vv">{best == null ? "—" : best.toFixed(2)}</span>
        <span className="vsub">of 1.00 possible</span>
      </div>
      <div className="vt">
        <span className="vk">Lessons kept</span>
        <span className="vv violet">{promotions}</span>
        <span className="vsub">promoted by the gate</span>
      </div>
      <div className="vt">
        <span className="vk">Integrity</span>
        <span className={`vv ${totViol === 0 ? "pos" : "neg"}`}>{totViol}</span>
        <span className="vsub">{totViol === 0 ? "no rules broken" : "rule breaks"}</span>
      </div>
    </div>
  );
}

/* episode outcomes table — only the columns the trace actually has, capped for scale */
function OutcomeTable({ rows }: { rows: Outcome[] }) {
  const [cap, setCap] = useState(150);
  const has = (k: keyof Outcome) => rows.some((o) => o[k] != null);
  const cols = { gen: has("gen"), reward: has("reward"), skill: has("skill"), surplus: has("surplus"), turns: has("turns"), bucket: has("bucket") };
  const deals = rows.filter((o) => o.deal).length;
  const prices = rows.filter((o) => o.deal && o.price != null).map((o) => o.price as number);
  const avgPrice = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null;
  const totViol = rows.reduce((s, o) => s + (o.viol || 0), 0);
  const view = rows.slice(0, cap);
  return (
    <>
      <div className="epiSummary">
        <span><b>{deals}</b>/{rows.length} closed</span>
        {avgPrice != null && <span>avg deal <b>{money(Math.round(avgPrice))}</b></span>}
        <span>integrity <Viol n={totViol} /></span>
      </div>
      <div className="otable-wrap">
        <table className="otable">
          <thead>
            <tr>
              {cols.gen && <th>gen</th>}<th>result</th>{cols.reward && <th>reward</th>}{cols.skill && <th>skill</th>}
              {cols.surplus && <th>surplus</th>}{cols.turns && <th>turns</th>}<th>viol</th>{cols.bucket && <th>bucket</th>}
            </tr>
          </thead>
          <tbody>
            {view.map((o, i) => (
              <tr key={i}>
                {cols.gen && <td className="c-dim">{o.gen ?? "—"}</td>}
                <td className={o.deal ? "res-deal" : "res-no"}>{o.deal ? money(o.price) : "no deal"}</td>
                {cols.reward && <td className="c-reward">{num2(o.reward)}</td>}
                {cols.skill && <td>{num2(o.skill)}</td>}
                {cols.surplus && <td>{num2(o.surplus)}</td>}
                {cols.turns && <td className="c-dim">{o.turns ?? "—"}</td>}
                <td className={o.viol === 0 ? "c-viol-clean" : "c-viol-bad"}>{o.viol}</td>
                {cols.bucket && <td className="c-dim">{o.bucket ?? "—"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > cap && <button className="moreBtn" onClick={() => setCap((c) => c + 200)}>Show {Math.min(200, rows.length - cap)} more of {rows.length}</button>}
    </>
  );
}

/* a transcript rendered as the face-off, capped for very long exchanges */
function Talk({ moves }: { moves: Move[] }) {
  const [cap, setCap] = useState(150);
  const view = moves.slice(0, cap);
  return (
    <>
      <div className="talk">
        {view.map((m, i) => (
          <div key={i} className={`turn ${m.role}`}>
            <span className="who">{m.role}{m.ts && <time className="mtime">{mclock(m.ts)}</time>}</span>
            <div className="bubble">
              <span className="say">{m.text || (m.action ? `(${m.action})` : "")}</span>
              {m.offer != null && <span className="offer">{money(m.offer)}</span>}
            </div>
          </div>
        ))}
      </div>
      {moves.length > cap && <button className="moreBtn" onClick={() => setCap((c) => c + 200)}>Show {Math.min(200, moves.length - cap)} more turns</button>}
    </>
  );
}

/* league sample transcripts — selectable, parsed into the same face-off */
export function Samples({ samples }: { samples: Sample[] }) {
  const [i, setI] = useState(0);
  const parsed = useMemo(() => samples.map((s) => parseTranscript(s.transcript)), [samples]);
  const s = samples[Math.min(i, samples.length - 1)];
  const moves = parsed[Math.min(i, samples.length - 1)] ?? [];
  return (
    <div className="samples">
      {samples.length > 1 && (
        <div className="sampleTabs" role="tablist" aria-label="Sample matches">
          {samples.map((sm, k) => (
            <button key={k} role="tab" aria-selected={k === i} className={`sampleTab ${k === i ? "on" : ""}`} onClick={() => setI(k)}>
              {sm.gen != null ? `gen ${sm.gen}` : `match ${k + 1}`}{sm.reward != null ? <span className="st-r"> · {num2(sm.reward)}</span> : null}
            </button>
          ))}
        </div>
      )}
      <div className="sampleMeta">
        {s.bucket && <span>bucket <code>{s.bucket}</code></span>}
        {s.item && <span>{s.item}</span>}
        {s.persona && <span>{s.persona}</span>}
        {s.reward != null && <span>reward {num2(s.reward)}</span>}
        {s.skill != null && <span>skill {num2(s.skill)}</span>}
        <span className="st-dim">{moves.length} turns</span>
      </div>
      <Talk moves={moves} />
    </div>
  );
}

/* the gate's decisions — what was kept vs discarded, with the Δ */
export function Gate({ events }: { events: RunEvent[] }) {
  const kind = (e: RunEvent) => (e.kind || e.verdict || "").toLowerCase();
  const cls = (k: string) => (k.includes("promot") ? "kept" : k.includes("reject") ? "cut" : k.includes("integ") ? "integ" : "esc");
  const label = (k: string) => (k.includes("promot") ? "kept" : k.includes("reject") ? "discarded" : k.includes("integ") ? "integrity" : "escalated");
  return (
    <div className="gate">
      {events.map((e, i) => {
        const k = kind(e); const c = cls(k);
        return (
          <div key={i} className={`gevent ${c}`}>
            <span className="gmark" />
            <span className="gverdict">{label(k)}</span>
            {e.gen != null && <span className="gdim">gen {e.gen}</span>}
            {e.bucket && <span className="gbucket">{e.bucket}</span>}
            {e.delta != null && <span className={`gdelta ${e.delta >= 0 ? "up" : "down"}`}>Δ {signed(e.delta)}</span>}
            {e.msg && <span className="gmsg">{e.msg}</span>}
          </div>
        );
      })}
    </div>
  );
}

function TransferPanel({ transfer }: { transfer: Transfer }) {
  const start = transfer.locked_start;
  const final = transfer.locked_final;
  const delta = transfer.locked_delta;
  const ok = transfer.transfer_ok ?? (delta != null && delta > 0 && final.viol === 0);
  return (
    <div className={`transfer ${ok ? "ok" : "bad"}`}>
      <div className="xferTop">
        <span className="xferVerdict">{ok ? "transfer passed" : "transfer failed"}</span>
        {delta != null && <span className={`xferDelta ${delta >= 0 ? "up" : "down"}`}>reward {signed(delta)}</span>}
      </div>
      <div className="xferGrid">
        <div><span className="xk">locked gen 0</span><b>{num2(start.reward)}</b><small>skill {num2(start.skill)} · viol {start.viol}</small></div>
        <div><span className="xk">locked final</span><b>{num2(final.reward)}</b><small>skill {num2(final.skill)} · viol {final.viol}</small></div>
        <div><span className="xk">yardstick</span><b>{final.n ?? start.n ?? "—"}</b><small>held-out episodes</small></div>
      </div>
    </div>
  );
}

export default function RunsPage() {
  const pathname = usePathname();
  const initialMode = pathname === "/history" ? "history" : "live";
  const [mode, setMode] = useState<ViewMode>(initialMode);
  const [live, setLive] = useState<LiveSnapshot>(blankLive);
  const [historyRuns, setHistoryRuns] = useState<Run[]>([]);
  const [historyConfigured, setHistoryConfigured] = useState(true);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [cat, setCat] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [historyDetail, setHistoryDetail] = useState<Detail | null>(null);
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [everFailed, setEverFailed] = useState(false);
  const reqRef = useRef(0);
  const historyAutoLoaded = useRef(false);

  /* ----- LIVE view: local JSONL SSE bus, never Logfire ----- */
  useEffect(() => {
    if (mode !== "live") return;
    const es = new EventSource(`${BACKEND}/watch/stream`);
    es.onopen = () => {
      setLive((prev) => ({ ...prev, connected: true, error: null }));
      setStatus((prev) => prev === "offline" ? "idle" : prev);
    };
    es.onmessage = (e) => {
      let ev: any;
      try { ev = JSON.parse(e.data); } catch { return; }
      setLive((prev) => applyWatchEvent(prev, ev));
      setStatus("idle");
      if (ev?.type === "done") es.close();
    };
    es.onerror = () => {
      setLive((prev) => ({ ...prev, connected: false, error: "watch stream disconnected" }));
      setStatus("offline");
      setEverFailed(true);
    };
    return () => es.close();
  }, [mode]);

  const loadHistory = useCallback(async () => {
    const my = ++reqRef.current;
    setMode("history");
    setStatus("loading");
    const ctrl = new AbortController();
    const to = setTimeout(() => ctrl.abort(), 14000);
    try {
      const r = await fetch(`${BACKEND}/runs`, { signal: ctrl.signal });
      const j = await r.json().catch(() => ({ error: "bad response" }));
      if (reqRef.current !== my) return;
      setHistoryConfigured(j.configured !== false);
      if (!r.ok || j.error) {
        setStatus(r.status === 429 || j.retry ? "throttled" : "error");
        setEverFailed(true);
        return;
      }
      const next: Run[] = j.runs ?? [];
      setHistoryRuns(next);
      setHistoryLoaded(true);
      setStatus("idle");
      setSelected((cur) => cur && next.some((run) => run.run_id === cur) ? cur : next[0]?.run_id ?? null);
    } catch (err: any) {
      if (reqRef.current !== my) return;
      setStatus(err?.name === "AbortError" ? "timeout" : "offline");
      setEverFailed(true);
    } finally {
      clearTimeout(to);
    }
  }, []);

  /* ----- history detail: explicit one-shot Logfire read, no live polling ----- */
  const fetchHistoryDetail = useCallback(async (rid: string) => {
    const my = ++reqRef.current;
    setHistoryDetail(null);
    setStatus("loading");
    const ctrl = new AbortController();
    const to = setTimeout(() => ctrl.abort(), 14000);
    try {
      const r = await fetch(`${BACKEND}/run?run_id=${encodeURIComponent(rid)}`, { signal: ctrl.signal });
      const j = await r.json().catch(() => ({ error: "bad response" }));
      if (reqRef.current !== my) return;
      if (r.status === 429 || j.retry) { setStatus("throttled"); setEverFailed(true); }
      else if (!r.ok || j.error) { setStatus("error"); setEverFailed(true); }
      else { setHistoryDetail(j); setStatus("idle"); }
    } catch (err: any) {
      if (reqRef.current !== my) return;
      setStatus(err?.name === "AbortError" ? "timeout" : "offline");
      setEverFailed(true);
    } finally {
      clearTimeout(to);
    }
  }, []);

  const liveRuns = useMemo(() => live.run ? [live.run] : [], [live.run]);
  const runs = mode === "live" ? liveRuns : historyRuns;
  const detail = mode === "live" ? (selected === live.detail?.run_id ? live.detail : null) : historyDetail;
  const selectedRun = useMemo(() => runs.find((r) => r.run_id === selected), [runs, selected]);
  const isLive = mode === "live" && !!selectedRun && !live.done;
  const streamReady = mode === "live" ? (live.connected || live.waiting || !!live.run || !!live.error) : historyLoaded || status !== "idle";
  const configured = mode === "live" ? true : historyConfigured;

  useEffect(() => {
    if (pathname === "/history") setMode("history");
  }, [pathname]);

  useEffect(() => { setEverFailed(false); }, [selected]);

  useEffect(() => {
    if (mode === "live" && live.run) setSelected(live.run.run_id);
  }, [mode, live.run?.run_id]);

  useEffect(() => {
    if (mode === "history" && !historyAutoLoaded.current) {
      historyAutoLoaded.current = true;
      loadHistory();
    }
  }, [mode, loadHistory]);

  useEffect(() => {
    if (mode !== "history" || !selected) return;
    fetchHistoryDetail(selected);
  }, [mode, selected, fetchHistoryDetail]);

  const openRun = useCallback((rid: string) => {
    setSelected(rid);
  }, []);

  const showLive = useCallback(() => {
    setMode("live");
    setStatus(live.error ? "offline" : "idle");
    setSelected(live.run?.run_id ?? null);
  }, [live.error, live.run?.run_id]);

  const cats = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of runs) m[r.category] = (m[r.category] ?? 0) + 1;
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [runs]);

  const agg = useMemo(() => {
    const rewarded = runs.filter((r) => r.mean_reward != null);
    return {
      episodes: runs.reduce((s, r) => s + (r.episodes || 0), 0),
      deals: runs.reduce((s, r) => s + (r.deals || 0), 0),
      viol: runs.reduce((s, r) => s + (r.viol || 0), 0),
      reward: rewarded.length ? rewarded.reduce((s, r) => s + (r.mean_reward as number), 0) / rewarded.length : null,
      rewardN: rewarded.length,
    };
  }, [runs]);

  const shown = useMemo(() => {
    const ql = query.trim().toLowerCase();
    return runs.filter((r) =>
      (cat === "all" || r.category === cat) &&
      (!ql || r.title.toLowerCase().includes(ql) || (r.buckets || []).join(" ").toLowerCase().includes(ql) || (r.run_id || "").toLowerCase().includes(ql))
    );
  }, [runs, cat, query]);

  const curve = detail?.curve ?? [];
  const hasClimb = curve.length > 0;
  const moves = detail?.moves ?? [];
  const samples = detail?.samples ?? [];
  const events = detail?.events ?? [];
  const reflections = detail?.reflections ?? [];
  const outcomes = detail?.outcomes ?? [];
  const transfer = detail?.transfer ?? null;
  const topTag = mode === "live" ? (live.error ? "error" : isLive ? "live" : "idle") : (configured ? "idle" : "error");
  const topLabel = mode === "live" ? (live.error ? "watch offline" : isLive ? "live · local bus" : "local replay") : (configured ? "trace archive" : "history unavailable");

  return (
    <main className="runs">
      <header className="rHead">
        <div>
          <span className={`tag ${topTag}`}>
            {topLabel}
          </span>
          {mode === "live" ? (
            <>
              <h1>Live held-out <em>transfer</em></h1>
              <p>The live view reads the local JSONL run bus directly: curve points, spotlight negotiations, and locked held-out transfer all arrive from <code>/watch/stream</code>.</p>
            </>
          ) : (
            <>
              <h1>Run <em>history</em></h1>
              <p>Every training run and haggle Gambit has logged. Open one to replay its climb, the lessons the optimizer kept, and every offer traded.</p>
            </>
          )}
        </div>
        <div className="headLinks">
          <Link href="/live" className="chatLink primary">Watch it climb <span className="arr">→</span></Link>
          <Link href="/chat" className="chatLink">Haggle the agent <span className="arr">→</span></Link>
          <ThemeToggle />
        </div>
      </header>

      <section className="summary" aria-label="Totals across every run">
        <div className="stat"><span className="k">Runs</span><span className="v num">{runs.length}</span></div>
        <div className="stat"><span className="k">Episodes</span><span className="v num">{agg.episodes.toLocaleString()}</span></div>
        <div className="stat"><span className="k">Deals closed</span><span className="v num">{agg.deals.toLocaleString()}</span></div>
        <div className="stat">
          <span className="k">Mean reward<small> · {agg.rewardN} run{agg.rewardN === 1 ? "" : "s"}</small></span>
          <span className="v num brass">{agg.reward == null ? "—" : agg.reward.toFixed(2)}</span>
        </div>
        <div className="stat"><span className="k">Integrity breaks</span><span className={`v num ${agg.viol === 0 ? "pos" : "neg"}`}>{agg.viol}</span></div>
      </section>

      <div className="filters">
        <button className={`chip all-chip ${mode === "live" ? "on" : ""}`} onClick={showLive} aria-pressed={mode === "live"}>
          <span className="cdot" />live <b>{live.run ? 1 : 0}</b>
        </button>
        <button className={`chip ${mode === "history" ? "on" : ""}`} onClick={loadHistory} aria-pressed={mode === "history"} style={{ ["--c" as any]: "#8a909c" }}>
          <span className="cdot" />history <b>{historyRuns.length}</b>
        </button>
        <button className={`chip ${cat === "all" ? "on" : ""}`} onClick={() => setCat("all")} aria-pressed={cat === "all"}>
          <span className="cdot" />all <b>{runs.length}</b>
        </button>
        {cats.map(([c, n]) => (
          <button key={c} className={`chip ${cat === c ? "on" : ""}`} onClick={() => setCat(c)} aria-pressed={cat === c} style={{ ["--c" as any]: catColor(c) }}>
            <span className="cdot" />{c} <b>{n}</b>
          </button>
        ))}
        <div className="searchWrap">
          <label htmlFor="runsearch" className="srOnly">Search runs</label>
          <input id="runsearch" className="search" placeholder="Search title, bucket, or run id…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        {mode === "history" && (
          <button className="moreBtn inline" onClick={loadHistory} disabled={status === "loading"}>{status === "loading" ? "Loading history..." : "Refresh history"}</button>
        )}
      </div>

      <div className="browser">
        <div className="runlist" role="listbox" aria-label="Runs">
          {!streamReady && shown.length === 0 && [0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="skRow"><span className="skel l1" /><span className="skel l2" /></div>
          ))}
          {streamReady && shown.length === 0 && (
            <div className="empty">
              <span className="glyph">{searchGlyph}</span>
              <span className="lead">{runs.length ? "Nothing matches" : mode === "live" ? "Waiting for a local run" : "No runs in the archive"}</span>
              <span className="hint">{runs.length ? "Try a different category or clear the search." : mode === "live" ? "The watcher will attach to runs/latest when a JSONL run appears." : "Past runs appear here as Gambit logs them. If the archive is rate-limited, wait a moment and Refresh history."}</span>
            </div>
          )}
          {shown.map((r) => {
            const liveRow = mode === "live" && r.run_id === live.run?.run_id && !live.done;
            return (
              <button key={r.run_id} role="option" aria-selected={selected === r.run_id}
                className={`runrow ${selected === r.run_id ? "sel" : ""}`} onClick={() => openRun(r.run_id)} style={{ ["--c" as any]: catColor(r.category) }}>
                <span className="rtop">
                  <span className="cbadge">{r.category}</span>
                  <span className="rtitle">{r.title}{r.source === "human" && <span className="srcdot"> · you</span>}</span>
                </span>
                <span className="rtime">{liveRow ? <span className="liveDot" /> : null}{fmt(r.ts)}</span>
                <span className="rmeta">
                  {r.episodes > 0 && <>{r.episodes} ep</>}
                  {r.deals > 0 && <><span className="sep">·</span>{r.deals} deal{r.deals > 1 ? "s" : ""}</>}
                  {r.mean_reward != null && <><span className="sep">·</span><span className="reward-v">reward {r.mean_reward.toFixed(2)}</span></>}
                  <span className="sep">·</span><Viol n={r.viol} blind={r.category === "offline-rl"} />
                  {r.buckets?.slice(0, 3).map((b) => <span key={b} className="btag">{b}</span>)}
                </span>
              </button>
            );
          })}
        </div>

        <div className="detail">
          {!selected && (
            <div className="empty">
              <span className="glyph">{curveGlyph}</span>
              <span className="lead">{mode === "live" ? "Watching the local run bus" : "Pick a history run"}</span>
              <span className="hint">{mode === "live" ? "The latest JSONL run will appear here as soon as /watch/stream announces it." : "Choose a run on the left to replay its climb, the lessons it kept, and every offer traded."}</span>
            </div>
          )}

          {/* first attempt: a short skeleton. once anything fails, the card below takes over and never reverts */}
          {selected && !detail && status === "loading" && !everFailed && (
            <div className="skDetail" aria-busy="true" aria-label="Loading run">
              <span className="skel title" />
              <div><span className="skel block" /></div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <span className="skel line" style={{ width: "70%" }} />
                <span className="skel line" style={{ width: "90%" }} />
                <span className="skel line" style={{ width: "55%" }} />
              </div>
            </div>
          )}
          {selected && !detail && (everFailed || (status !== "loading" && status !== "idle")) && (() => {
            const retrying = status === "loading";
            const offline = status === "offline";
            const errored = status === "error";
            return (
              <div className={`empty ${errored ? "err" : ""}`}>
                <span className={`glyph ${retrying ? "spin" : ""}`}>{errored || offline ? warnGlyph : hourglassGlyph}</span>
                <span className="lead">
                  {offline ? "Can't reach the backend" : errored ? "Couldn't load this run" : "The archive is rate-limited"}
                </span>
                <span className="hint">
                  {offline ? (mode === "live" ? "The local watch stream is not connected. Check the backend or wait for it to reconnect." : "The trace service isn't responding. It may be restarting.")
                    : errored ? "Something went wrong reading this run."
                    : "The history API caps reads per minute, so this request is queued."}
                  {retrying ? " Retrying now..." : status === "throttled" || status === "timeout" ? " Try again after the rate gate clears." : ""}
                </span>
                {mode === "history" && <button className="retryBtn" onClick={() => selected && fetchHistoryDetail(selected)} disabled={retrying}>{retrying ? "Retrying..." : "Retry now"}</button>}
              </div>
            );
          })()}

          {detail && (
	            <>
	              <header className="dhead">
	                <div className="dhTop">
	                  <h2 className="dtitle">{detail.title ?? selectedRun?.title ?? "Run"}</h2>
	                  {selectedRun && (
	                    <span className={`tag ${isLive ? "live" : "idle"} small`}>{isLive ? "live · local bus" : mode === "live" ? "complete · local bus" : `history · ${relAge(selectedRun.ts)}`}</span>
	                  )}
	                </div>
                {selectedRun && (
                  <p className="dsub">
                    <Tip k={selectedRun.category}>{selectedRun.category}</Tip>
                    <span className="sep">·</span><span>{fmt(selectedRun.ts)}</span>
                    {selectedRun.checkpoint && <><span className="sep">·</span><span>checkpoint {selectedRun.checkpoint}</span></>}
                    {status === "throttled" && mode === "history" && detail && <><span className="sep">·</span><span className="throttleNote">history refresh rate-limited</span></>}
                  </p>
                )}
              </header>

              {hasClimb && (
                <section className="dsec hero">
	                  <h3>The climb <span className="sub">held-out reward by generation</span></h3>
	                  <Climb curve={curve} live={isLive} />
	                  <Vitals curve={curve} run={selectedRun} />
	                </section>
	              )}

              {transfer && (
                <section className="dsec">
                  <h3>Locked transfer <span className="sub">held-out family</span></h3>
                  <TransferPanel transfer={transfer} />
                </section>
              )}

              {events.length > 0 && (
                <section className="dsec">
                  <h3>The gate <span className="sub">{events.length} decision{events.length === 1 ? "" : "s"}</span></h3>
                  <p className="secLead">Each Gemini lesson is replayed on held-out matches. It's <Tip k="promotion">kept</Tip> only if it raises reward, otherwise <Tip k="rejection">discarded</Tip>.</p>
                  <Gate events={events} />
                </section>
              )}

              {reflections.length > 0 && (
                <section className="dsec gemini">
                  <h3>What the Gemini optimizer wrote <span className="sub">{reflections.length} lesson{reflections.length === 1 ? "" : "s"}</span></h3>
                  {reflections.map((r, i) => (
                    <div key={i} className="ref">
                      <div className="refHead">
                        <span className="refBucket">bucket <code>{r.bucket ?? "—"}</code></span>
                        {r.surplus != null && <><span className="sep">·</span><span>surplus {num2(r.surplus)}</span></>}
                        <span className="sep">·</span><Viol n={r.viol} />
                      </div>
                      {r.seller_lesson && <div className="lesson seller"><span className="lblabel">seller</span><p>{r.seller_lesson}</p></div>}
                      {r.buyer_lesson && <div className="lesson buyer"><span className="lblabel">buyer</span><p>{r.buyer_lesson}</p></div>}
                    </div>
                  ))}
                </section>
              )}

              {moves.length > 0 && (
                <section className="dsec">
                  <h3>The negotiation <span className="sub">{moves.length} turns</span></h3>
                  <Talk moves={moves} />
                  {outcomes.length === 1 && (
                    <div className={`epOut ${outcomes[0].deal ? "deal" : "nodeal"}`}>
                      {outcomes[0].deal ? (
                        <>
                          <span className="lead">Deal</span>{money(outcomes[0].price)}
                          <span>reward {num2(outcomes[0].reward)}</span>
                          <span><Tip k="skill">skill</Tip> {num2(outcomes[0].skill)}</span>
                          {outcomes[0].surplus != null && <span>surplus {num2(outcomes[0].surplus)}</span>}
                          {outcomes[0].turns != null && <span>{outcomes[0].turns} turns</span>}
                        </>
                      ) : (<><span className="lead">No deal</span><span>{outcomes[0].result}</span></>)}
                    </div>
                  )}
                </section>
              )}

              {moves.length === 0 && samples.length > 0 && (
                <section className="dsec">
                  <h3>Sample matches <span className="sub">{samples.length} from this run</span></h3>
                  <Samples samples={samples} />
                </section>
              )}

              {outcomes.length > 1 && (
                <section className="dsec">
                  <h3>Episodes <span className="sub">{outcomes.length}</span></h3>
                  <OutcomeTable rows={outcomes} />
                </section>
              )}

              {!hasClimb && !transfer && moves.length === 0 && samples.length === 0 && reflections.length === 0 && events.length === 0 && outcomes.length === 0 && (
                <div className="empty">
                  <span className="glyph">{metricsGlyph}</span>
                  <span className="lead">No trace detail yet</span>
                  <span className="hint">This run logged numbers, not a transcript{detail.spans ? ` (${detail.spans} spans)` : ""}. Self-play runs show the climb and the lessons; human-play runs show the full exchange.</span>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </main>
  );
}

/* inline state glyphs — quiet line art, not spinners */
const searchGlyph = (
  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
);
const curveGlyph = (
  <svg width="42" height="42" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 38h36" opacity="0.5" /><path d="M8 34c6-1 9-9 14-14s9-9 18-12" /><circle cx="40" cy="8" r="2.5" fill="currentColor" stroke="none" /></svg>
);
const warnGlyph = (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4" /><circle cx="12" cy="17" r="0.6" fill="currentColor" /></svg>
);
const hourglassGlyph = (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3h12M6 21h12M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9" /></svg>
);
const metricsGlyph = (
  <svg width="40" height="40" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 40V20M20 40V10M32 40V26M44 40V16" /><path d="M4 40h40" opacity="0.5" /></svg>
);

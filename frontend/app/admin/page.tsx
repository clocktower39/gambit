"use client";

// Password-protected admin dashboard. Two panels:
//   1. Floors — the secret reserve the live seller defends (fetched via /api/admin/floors, which
//      proxies to the Basic-Auth-gated Python endpoint; credentials live only in .env / ADMIN_USERS).
//   2. Live feed — human-vs-agent chats as they happen. Reuses the existing public /runs/stream SSE
//      (which re-emits on every turn, since each move bumps the run's updated_ts) + /run for detail.
// The gate is client-side; the only true secret (floors) is enforced server-side, so an unauthenticated
// visitor sees the login form and nothing else useful.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const BACKEND = process.env.NEXT_PUBLIC_AGUI_HTTP ?? "http://localhost:8000";
const TOKEN_KEY = "gambit_admin_token";

type Floor = {
  id: number; name: string; condition: string; description: string;
  list_price: number; target: number; floor: number; sim_floor: number; sim_target: number;
  bucket: string; margin_pct: number;
};
type FloorsResp = { policy: string; items: Floor[] };

type Run = {
  run_id: string; ts: string; updated_ts?: string; category: string; source: string | null;
  title: string; checkpoint: string | null; episodes: number; deals: number;
  mean_reward: number | null; viol: number; buckets: string[];
};
type Move = { role: "seller" | "buyer"; action?: string | null; offer: number | null; text: string };
type Outcome = { result: string; deal: boolean; price: number | null; surplus: number | null; turns: number | null };
type Detail = { run_id: string; title: string | null; moves: Move[]; outcomes: Outcome[]; updated_ts?: string | null };

const money = (v: number | null | undefined) => (v == null ? "—" : `$${Number.isInteger(v) ? v : v.toFixed(2)}`);
const ageMs = (ts?: string) => { if (!ts) return Infinity; const t = Date.parse(ts); return Number.isNaN(t) ? Infinity : Date.now() - t; };
const fmt = (ts?: string) => { if (!ts) return ""; try { return new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); } catch { return ts; } };

/* ---------------- login gate ---------------- */
function Login({ onAuthed }: { onAuthed: (token: string, floors: Floor[]) => void }) {
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    const token = btoa(`${user}:${pass}`);
    try {
      const res = await fetch("/api/admin/floors", { headers: { authorization: `Basic ${token}` }, cache: "no-store" });
      if (res.status === 401) { setErr("Wrong username or password."); return; }
      if (res.status === 503) { setErr("Admin is not configured (set ADMIN_USERS in .env)."); return; }
      if (!res.ok) { setErr(`Unexpected error (${res.status}).`); return; }
      const data: FloorsResp = await res.json();
      onAuthed(token, data.items);
    } catch {
      setErr("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="adminGate">
      <form className="adminCard adminLogin" onSubmit={submit}>
        <div className="adminBrand">Gambit · admin</div>
        <p className="adminSub">Sign in to view reserves and the live haggle feed.</p>
        <label>Username<input autoFocus value={user} onChange={(e) => setUser(e.target.value)} autoComplete="username" /></label>
        <label>Password<input type="password" value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="current-password" /></label>
        {err && <div className="adminErr">{err}</div>}
        <button type="submit" disabled={busy || !user}>{busy ? "Checking…" : "Sign in"}</button>
      </form>
    </div>
  );
}

/* ---------------- transcript (mirrors the /history Talk component) ---------------- */
function Talk({ moves }: { moves: Move[] }) {
  if (!moves.length) return <div className="empty">No turns yet — waiting for the first message.</div>;
  return (
    <div className="talk">
      {moves.map((m, i) => (
        <div key={i} className={`turn ${m.role}`}>
          <span className="who">{m.role}</span>
          <div className="bubble">
            <span className="say">{m.text || (m.action ? `(${m.action})` : "")}</span>
            {m.offer != null && <span className="offer">{money(m.offer)}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------------- dashboard ---------------- */
function Dashboard({ token, floors, onLogout }: { token: string; floors: Floor[]; onLogout: () => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selId, setSelId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  // live run list via the existing public SSE (re-emits whenever any run is touched)
  useEffect(() => {
    const es = new EventSource(`${BACKEND}/runs/stream`);
    esRef.current = es;
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "runs" && Array.isArray(msg.runs)) {
          const human = (msg.runs as Run[]).filter((r) => r.category === "human-vs-agent");
          setRuns(human);
        }
      } catch { /* keepalive / non-JSON */ }
    };
    return () => { es.close(); esRef.current = null; };
  }, []);

  // default-select the most recently active chat
  useEffect(() => {
    if (!selId && runs.length) setSelId(runs[0].run_id);
  }, [runs, selId]);

  // (re)fetch the selected transcript whenever it's chosen or its updated_ts advances (a new turn)
  const selUpdated = useMemo(() => runs.find((r) => r.run_id === selId)?.updated_ts, [runs, selId]);
  useEffect(() => {
    if (!selId) { setDetail(null); return; }
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`${BACKEND}/run?run_id=${encodeURIComponent(selId)}`, { cache: "no-store" });
        if (!res.ok) return;
        const d: Detail = await res.json();
        if (alive) setDetail(d);
      } catch { /* transient */ }
    })();
    return () => { alive = false; };
  }, [selId, selUpdated]);

  const logout = () => { try { sessionStorage.removeItem(TOKEN_KEY); } catch { } esRef.current?.close(); onLogout(); };
  void token; // kept for symmetry; floor data already fetched at login

  const sel = runs.find((r) => r.run_id === selId) || null;
  const liveCount = runs.filter((r) => ageMs(r.updated_ts) < 30_000).length;

  return (
    <div className="adminWrap">
      <header className="adminTop">
        <div className="adminBrand">Gambit · admin</div>
        <nav className="adminNav">
          <Link href="/live">live climb</Link>
          <Link href="/history">history</Link>
          <Link href="/chat">chat</Link>
          <button className="adminLogout" onClick={logout}>Sign out</button>
        </nav>
      </header>

      {/* Floors */}
      <section className="adminSec">
        <h2>Reserve prices <span className="adminHint">what the seller will actually accept</span></h2>
        <div className="floorGrid">
          {floors.map((f) => (
            <div key={f.id} className="floorCard">
              <div className="floorName">{f.name}</div>
              <div className="floorCond">{f.condition} · {f.bucket.split("/")[0]} margin</div>
              <div className="floorRow"><span>List</span><b>{money(f.list_price)}</b></div>
              <div className="floorRow"><span>Target</span><b>{money(f.target)}</b></div>
              <div className="floorRow floorFloor"><span>Floor</span><b>{money(f.floor)}</b></div>
              <div className="floorRow muted"><span>Sim floor</span><span>{money(f.sim_floor)}</span></div>
              <div className="floorBar"><div className="floorBarFill" style={{ width: `${100 - f.margin_pct}%` }} /></div>
              <div className="floorMargin">floor is {100 - f.margin_pct}% of list · {f.margin_pct}% max discount</div>
            </div>
          ))}
        </div>
      </section>

      {/* Live feed */}
      <section className="adminSec">
        <h2>
          Live haggles <span className="adminHint">human vs. the trained seller</span>
          <span className={`tag ${connected ? "live" : "idle"}`} style={{ marginLeft: 10 }}>
            {connected ? `${liveCount} active` : "reconnecting…"}
          </span>
        </h2>
        <div className="adminBrowser">
          <div className="adminRunlist">
            {runs.length === 0 && <div className="empty">No human chats yet. Open <Link href="/chat">/chat</Link> and haggle to see it appear here live.</div>}
            {runs.map((r) => {
              const live = ageMs(r.updated_ts) < 30_000;
              return (
                <button key={r.run_id} className={`adminRunrow ${r.run_id === selId ? "on" : ""}`} onClick={() => setSelId(r.run_id)}>
                  <div className="rrTitle">{r.title || r.run_id}{live && <span className="rrLive" />}</div>
                  <div className="rrMeta">
                    {r.deals > 0 ? <span className="rrDeal">deal</span> : <span className="rrOpen">open</span>}
                    <span>{fmt(r.updated_ts || r.ts)}</span>
                  </div>
                </button>
              );
            })}
          </div>
          <div className="adminDetail">
            {sel ? (
              <>
                <div className="adminDetailHead">
                  <div className="rrTitle">{sel.title || sel.run_id}</div>
                  <div className="rrMeta">{detail?.moves?.length ?? 0} turns · {fmt(sel.updated_ts || sel.ts)}</div>
                </div>
                {detail?.outcomes?.[0] && (
                  <div className="adminOutcome">
                    {detail.outcomes[0].deal
                      ? <>Sold at <b>{money(detail.outcomes[0].price)}</b>{detail.outcomes[0].surplus != null && <> · surplus {money(detail.outcomes[0].surplus)}</>}</>
                      : <>Result: <b>{detail.outcomes[0].result || "walked"}</b></>}
                  </div>
                )}
                <Talk moves={detail?.moves ?? []} />
              </>
            ) : <div className="empty">Select a chat to watch it unfold.</div>}
          </div>
        </div>
      </section>

      <style>{adminCss}</style>
    </div>
  );
}

/* ---------------- root: gate then dashboard ---------------- */
export default function AdminPage() {
  const [token, setToken] = useState<string | null>(null);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [checking, setChecking] = useState(true);

  // restore a prior session: re-validate the stored token (also re-fetches fresh floors)
  useEffect(() => {
    let alive = true;
    const stored = (() => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } })();
    if (!stored) { setChecking(false); return; }
    (async () => {
      try {
        const res = await fetch("/api/admin/floors", { headers: { authorization: `Basic ${stored}` }, cache: "no-store" });
        if (res.ok) {
          const data: FloorsResp = await res.json();
          if (alive) { setToken(stored); setFloors(data.items); }
        } else {
          try { sessionStorage.removeItem(TOKEN_KEY); } catch { }
        }
      } catch { /* offline — show login */ }
      finally { if (alive) setChecking(false); }
    })();
    return () => { alive = false; };
  }, []);

  const onAuthed = useCallback((t: string, f: Floor[]) => {
    try { sessionStorage.setItem(TOKEN_KEY, t); } catch { }
    setToken(t); setFloors(f);
  }, []);
  const onLogout = useCallback(() => { setToken(null); setFloors([]); }, []);

  if (checking) return <div className="adminGate"><div className="adminCard">Loading…</div><style>{adminCss}</style></div>;
  if (!token) return <><Login onAuthed={onAuthed} /><style>{adminCss}</style></>;
  return <Dashboard token={token} floors={floors} onLogout={onLogout} />;
}

/* ---------------- styles (brand tokens from globals.css) ---------------- */
const adminCss = `
.adminGate { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg); padding: 24px; }
.adminCard { background: var(--panel); border: 1px solid var(--line); border-radius: var(--r-md, 14px); padding: 28px; color: var(--ink); }
.adminLogin { width: 340px; max-width: 100%; display: flex; flex-direction: column; gap: 14px; }
.adminBrand { font-family: var(--font-display, serif); font-size: 22px; font-weight: 600; color: var(--brass); letter-spacing: -0.5px; }
.adminSub { margin: -6px 0 4px; color: var(--muted); font-size: 14px; }
.adminLogin label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--ink-dim, #b9c0cc); }
.adminLogin input { background: var(--panel-2, #0f1219); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; color: var(--ink); font-size: 15px; }
.adminLogin input:focus { outline: none; border-color: var(--brass); }
.adminLogin button { margin-top: 6px; background: var(--brass); color: #1a1206; border: 0; border-radius: 8px; padding: 11px; font-weight: 600; font-size: 15px; cursor: pointer; }
.adminLogin button:disabled { opacity: 0.6; cursor: default; }
.adminErr { color: var(--neg, #e06a6a); font-size: 13px; }

.adminWrap { max-width: var(--maxw, 1520px); margin: 0 auto; padding: 22px clamp(16px, 4vw, 40px) 60px; color: var(--ink); }
.adminTop { display: flex; align-items: center; justify-content: space-between; padding-bottom: 18px; border-bottom: 1px solid var(--line); margin-bottom: 26px; }
.adminNav { display: flex; align-items: center; gap: 18px; }
.adminNav a { color: var(--muted); text-decoration: none; font-size: 14px; }
.adminNav a:hover { color: var(--ink); }
.adminLogout { background: transparent; border: 1px solid var(--line); color: var(--muted); border-radius: 8px; padding: 7px 14px; cursor: pointer; font-size: 14px; }
.adminLogout:hover { color: var(--ink); border-color: var(--brass); }

.adminSec { margin-bottom: 38px; }
.adminSec h2 { font-family: var(--font-display, serif); font-size: 20px; font-weight: 600; margin: 0 0 16px; display: flex; align-items: center; }
.adminHint { font-family: var(--font-sans, sans-serif); font-size: 13px; font-weight: 400; color: var(--muted); margin-left: 10px; }

.floorGrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
.floorCard { background: var(--panel); border: 1px solid var(--line); border-radius: var(--r-md, 14px); padding: 18px 20px; }
.floorName { font-size: 16px; font-weight: 600; color: var(--ink); }
.floorCond { font-size: 12px; color: var(--muted); margin: 2px 0 14px; text-transform: capitalize; }
.floorRow { display: flex; justify-content: space-between; align-items: baseline; padding: 4px 0; font-size: 14px; color: var(--ink-dim, #b9c0cc); }
.floorRow b { color: var(--ink); font-variant-numeric: tabular-nums; }
.floorFloor { border-top: 1px solid var(--line); margin-top: 6px; padding-top: 10px; }
.floorFloor b { color: var(--brass); font-size: 18px; }
.floorRow.muted { font-size: 12px; color: var(--faint, #6b7280); }
.floorBar { height: 6px; background: var(--panel-2, #0f1219); border-radius: 4px; margin: 14px 0 6px; overflow: hidden; }
.floorBarFill { height: 100%; background: linear-gradient(90deg, var(--brass), var(--pos, #4fd1a8)); }
.floorMargin { font-size: 11px; color: var(--muted); }

.adminBrowser { display: grid; grid-template-columns: 300px 1fr; gap: 16px; align-items: start; }
.adminRunlist { display: flex; flex-direction: column; gap: 8px; max-height: 560px; overflow-y: auto; }
.adminRunrow { text-align: left; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; cursor: pointer; color: var(--ink); }
.adminRunrow:hover { border-color: var(--brass); }
.adminRunrow.on { border-color: var(--brass); background: var(--panel-2, #0f1219); }
.rrTitle { font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 8px; }
.rrLive { width: 8px; height: 8px; border-radius: 50%; background: var(--pos, #4fd1a8); box-shadow: 0 0 0 0 rgba(79,209,168,0.6); animation: rrpulse 1.6s infinite; }
@keyframes rrpulse { 0% { box-shadow: 0 0 0 0 rgba(79,209,168,0.5); } 70% { box-shadow: 0 0 0 7px rgba(79,209,168,0); } 100% { box-shadow: 0 0 0 0 rgba(79,209,168,0); } }
.rrMeta { display: flex; gap: 10px; align-items: center; font-size: 12px; color: var(--muted); margin-top: 5px; }
.rrDeal { color: var(--pos, #4fd1a8); }
.rrOpen { color: var(--brass); }
.adminDetail { background: var(--panel); border: 1px solid var(--line); border-radius: var(--r-md, 14px); padding: 18px 20px; min-height: 300px; }
.adminDetailHead { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--line); padding-bottom: 12px; margin-bottom: 14px; }
.adminOutcome { font-size: 14px; color: var(--ink-dim, #b9c0cc); margin-bottom: 14px; }
.adminOutcome b { color: var(--ink); }
.empty { color: var(--muted); font-size: 14px; padding: 20px 0; }

@media (max-width: 760px) { .adminBrowser { grid-template-columns: 1fr; } }
`;

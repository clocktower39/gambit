"use client";

// The PRIMARY demo surface: a full-page, live view to watch a self-improving negotiator CLIMB.
// Consumes the local JSONL bus (GET /watch/stream) — fast, no rate limit. Self-contained on
// purpose (own curve/vitals/feed, scoped <style>) so it's robust to the rest of the app churning.

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import ThemeToggle from "../ThemeToggle";

const BACKEND = process.env.NEXT_PUBLIC_AGUI_HTTP ?? "http://localhost:8000";

type Move = { role: "seller" | "buyer"; action?: string | null; offer: number | null; text: string };
type CurvePt = { gen: number; reward: number | null; skill: number | null; viol: number; promoted: boolean };
type Episode = {
  gen: number; seed: number; item: string; list_price: number; floor_price: number;
  persona: string; bucket: string; moves: Move[];
  outcome: { deal: boolean; price: number | null; turns: number; surplus?: number; skill?: number; reason?: string };
};
type Transfer = {
  locked_start: { reward: number; skill: number; viol: number };
  locked_final: { reward: number; skill: number; viol: number };
  locked_delta: number;
};
type Status = "waiting" | "live" | "done";

const money = (v: number | null | undefined) => (v == null ? "—" : `$${Number.isInteger(v) ? v : v.toFixed(2)}`);
const signed = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;

// ---------- the hero: reward + skill by generation, anchored 0..1 ----------
function Climb({ curve, live }: { curve: CurvePt[]; live: boolean }) {
  const W = 1000, H = 360, padL = 48, padR = 24, padT = 28, padB = 38;
  const maxG = Math.max(1, ...curve.map((p) => p.gen));
  const x = (g: number) => padL + (g / maxG) * (W - padL - padR);
  const y = (v: number) => H - padB - Math.max(0, Math.min(1, v)) * (H - padT - padB);
  const r = curve.filter((p) => p.reward != null) as (CurvePt & { reward: number })[];
  const s = curve.filter((p) => p.skill != null) as (CurvePt & { skill: number })[];
  const line = (pts: any[], k: "reward" | "skill") => pts.map((p, i) => `${i ? "L" : "M"}${x(p.gen).toFixed(1)},${y(p[k]).toFixed(1)}`).join(" ");
  const rLine = line(r, "reward"), sLine = line(s, "skill");
  const baseY = y(0).toFixed(1);
  const area = r.length > 1 ? `${rLine} L${x(r[r.length - 1].gen).toFixed(1)},${baseY} L${x(r[0].gen).toFixed(1)},${baseY} Z` : "";
  const showDots = r.length <= 48;
  const last = r[r.length - 1];

  return (
    <div className="climb">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Held-out reward by generation, 0 to 1">
        <defs>
          <linearGradient id="rfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#d9a24a" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#d9a24a" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={padL} y1={y(v)} x2={W - padR} y2={y(v)} className={`grid ${v === 0 ? "base" : ""}`} />
            <text x={padL - 10} y={y(v) + 3.5} textAnchor="end" className="axis">{v}</text>
          </g>
        ))}
        {curve.length > 1 && curve.map((p) => (
          <text key={p.gen} x={x(p.gen)} y={H - padB + 17} textAnchor="middle" className="gtick">{p.gen}</text>
        ))}
        {area && <path d={area} fill="url(#rfill)" />}
        {sLine && <path d={sLine} className="lSkill" fill="none" />}
        {rLine && <path d={rLine} className="lReward" fill="none" />}
        {showDots && r.filter((p) => p.promoted).map((p) => (
          <path key={`p${p.gen}`} d="M0,-7 L6,0 L0,7 L-6,0 Z" className="promo" transform={`translate(${x(p.gen)},${y(p.reward)})`} />
        ))}
        {showDots && r.map((p, i) => (
          <circle key={p.gen} cx={x(p.gen)} cy={y(p.reward)} r={i === r.length - 1 ? 5 : 3.2} className={`dot ${p.promoted ? "kept" : ""}`} />
        ))}
        {live && last && <circle cx={x(last.gen)} cy={y(last.reward)} r="5" className="pulse" />}
        {r.length === 0 && <text x={W / 2} y={H / 2} textAnchor="middle" className="warm">held-out reward lands as the run plays…</text>}
      </svg>
      <div className="foot">
        <span className="lg"><i className="sw rw" />held-out reward</span>
        {s.length > 0 && <span className="lg"><i className="sw sk" />skill</span>}
        <span className="lg"><i className="sw pr" />lesson kept</span>
        {r.length === 1 && <span className="note">gen 0 · the curve grows as it runs</span>}
      </div>
    </div>
  );
}

function Vitals({ curve }: { curve: CurvePt[] }) {
  const r = curve.filter((p) => p.reward != null).map((p) => p.reward as number);
  const cur = r.length ? r[r.length - 1] : null;
  const base = r.length ? r[0] : null;
  const best = r.length ? Math.max(...r) : null;
  const delta = cur != null && base != null ? cur - base : null;
  const kept = curve.filter((p) => p.promoted).length;
  const viol = curve.reduce((a, p) => a + (p.viol || 0), 0);
  return (
    <div className="vitals">
      <div className="vt"><span className="vk">Generations</span><span className="vv">{curve.length || 0}</span></div>
      <div className="vt"><span className="vk">{r.length > 1 ? "Reward now" : "Reward"}</span><span className="vv brass">{cur == null ? "—" : cur.toFixed(2)}</span>
        <span className="vsub">{delta == null ? "of 1.00" : <>from {base!.toFixed(2)} · <b className={delta < 0 ? "dn" : "up"}>{signed(delta)}</b></>}</span></div>
      <div className="vt"><span className="vk">Best held-out</span><span className="vv">{best == null ? "—" : best.toFixed(2)}</span></div>
      <div className="vt"><span className="vk">Lessons kept</span><span className="vv">{kept}</span></div>
      <div className="vt"><span className="vk">Integrity</span><span className={`vv ${viol === 0 ? "ok" : "bad"}`}>viol {viol}</span></div>
    </div>
  );
}

export default function LivePage() {
  const [curve, setCurve] = useState<CurvePt[]>([]);
  const [spots, setSpots] = useState<Episode[]>([]);
  const [transfer, setTransfer] = useState<Transfer | null>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("waiting");
  const [starting, setStarting] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const connect = useCallback((targetRunId?: string) => {
    esRef.current?.close();
    setCurve([]); setSpots([]); setTransfer(null); setCfg(null); setRunId(targetRunId ?? null); setStatus("waiting");
    const qs = targetRunId ? `?run=${encodeURIComponent(targetRunId)}` : "";
    const es = new EventSource(`${BACKEND}/watch/stream${qs}`);
    esRef.current = es;
    es.onmessage = (e) => {
      let ev: any;
      try { ev = JSON.parse(e.data); } catch { return; }
      switch (ev.type) {
        case "start": setCfg(ev); setStatus("live"); break;
        case "run":
          setRunId(ev.run_id);
          setCurve([]); setSpots([]); setTransfer(null); setCfg(null);
          setStatus("live");
          break;
        case "gen":
          setStatus("live");
          setCurve((c) => [...c.filter((p) => p.gen !== ev.gen), { gen: ev.gen, reward: ev.reward, skill: ev.skill, viol: ev.viol, promoted: !!ev.improved }].sort((a, b) => a.gen - b.gen));
          break;
        case "episode": setSpots((s) => [ev, ...s].slice(0, 16)); break;
        case "transfer": setTransfer(ev); break;
        case "done": setStatus("done"); break;
      }
    };
  }, []);

  useEffect(() => { connect(); return () => esRef.current?.close(); }, [connect]);

  const runFresh = useCallback(async () => {
    setStarting(true);
    try {
      const r = await fetch(`${BACKEND}/watch/start`, { method: "POST" });
      const body = await r.json().catch(() => ({}));
      connect(body.run_id);
    }
    finally { setStarting(false); }
  }, [connect]);

  return (
    <main className="live">
      <header className="head">
        <div>
          <span className={`tag ${status}`}>
            {status === "live" ? "● live · watching it climb" : status === "done" ? "● run complete" : "○ waiting for a run"}
            {runId ? ` · ${runId}` : ""}
          </span>
          <h1>Watch it <em>climb</em></h1>
          <p>
            A negotiator that trains itself. Each generation it rewrites its own tactics, keeps only
            what beats a <b>held-out</b> yardstick with integrity intact (<b>viol 0</b>), and climbs.
            {cfg && <> Training vs <b>{cfg.train_family}</b>, judged on the never-trained <b>{cfg.locked_family}</b>.</>}
          </p>
        </div>
        <div className="ctrls">
          <button className="btn" onClick={runFresh} disabled={starting || status === "live"}>
            {starting ? "starting…" : status === "live" ? "running…" : "▶ Run a fresh climb"}
          </button>
          <Link href="/history" className="btn ghost">Browse past runs →</Link>
          <ThemeToggle />
        </div>
      </header>

      <section className="stage" aria-label="Live climb and negotiations">
        <div className="climbPane">
          <section className="hero">
            <Climb curve={curve} live={status === "live"} />
            <Vitals curve={curve} />
          </section>

          {transfer && (
            <section className="transfer">
              <b>It generalizes.</b> On <b>{cfg?.locked_family ?? "a held-out family"}</b> it never trained against,
              held-out reward climbed <b>{transfer.locked_start.reward.toFixed(3)} → {transfer.locked_final.reward.toFixed(3)}</b>
              {" "}(<b className="up">{signed(transfer.locked_delta)}</b>), skill {transfer.locked_start.skill.toFixed(2)} → {transfer.locked_final.skill.toFixed(2)},
              with <b className="ok">viol {transfer.locked_final.viol}</b>.
            </section>
          )}
        </div>

        <section className="feedwrap">
          <div className="feedHead">
            <h3>Live negotiations</h3>
            <span>{spots.length ? `${spots.length} streamed` : "waiting for chats"}</span>
          </div>
          <div className="feed">
            {spots.length === 0 && <div className="empty">negotiations stream here as the run plays…</div>}
            {spots.map((ep, i) => (
              <article className={`spot ${i === 0 ? "latest" : ""}`} key={`${ep.gen}-${ep.seed}-${i}`}>
                <div className="spotHead">
                  <b>{ep.item}</b>
                  <span>gen {ep.gen} · vs {ep.persona} · <code>{ep.bucket}</code></span>
                </div>
                <div className="talk">
                  {ep.moves.map((m, k) => (
                    <div className={`turn ${m.role}`} key={k}>
                      <span className="who">{m.role}</span>
                      <div className="bubble">
                        <span className="say">{m.text || (m.action ? `(${m.action})` : "")}</span>
                        {m.offer != null && <span className="offer">{money(m.offer)}</span>}
                      </div>
                    </div>
                  ))}
                </div>
                <div className={`spotOut ${ep.outcome.deal ? "deal" : "nodeal"}`}>
                  {ep.outcome.deal ? `deal ${money(ep.outcome.price)} · ${ep.outcome.turns} turns` : `no deal${ep.outcome.reason ? ` (${ep.outcome.reason})` : ""}`}
                </div>
              </article>
            ))}
          </div>
        </section>
      </section>

      <style>{liveCss}</style>
    </main>
  );
}

const liveCss = `
.live{--brass:#d9a24a;--brass2:#f0c074;--pos:#4fd1a8;--neg:#f0676b;--ink:#ece9e3;--dim:#c4c2bc;--muted:#868c98;--panel:#14171f;--panel2:#10131b;--line:#232936;--seller:#6ea8ff;--buyer:#e0a85a;
  max-width:1560px;margin:0 auto;padding:24px 26px 38px;color:var(--ink);}
.live .head{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;}
.live .tag{display:inline-flex;align-items:center;gap:7px;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:4px 11px;margin-bottom:14px;}
.live .tag.live{color:var(--pos);border-color:rgba(79,209,168,.4);}
.live .tag.done{color:var(--brass2);border-color:rgba(217,162,74,.4);}
.live h1{font-family:Fraunces,Georgia,serif;font-weight:500;font-size:clamp(28px,3.7vw,42px);letter-spacing:-.025em;margin:0 0 8px;}
.live h1 em{font-style:italic;color:var(--brass2);font-weight:400;}
.live .head p{color:var(--dim);max-width:720px;font-size:14px;line-height:1.5;margin:0;}
.live .ctrls{display:flex;gap:10px;align-items:center;}
.live .btn{font-size:13.5px;font-weight:600;color:#1a130a;background:linear-gradient(180deg,var(--brass2),var(--brass));border:0;border-radius:999px;padding:9px 16px;cursor:pointer;white-space:nowrap;}
.live .btn:disabled{opacity:.5;cursor:default;}
.live .btn.ghost{color:var(--ink);background:transparent;border:1px solid var(--line);}
.live .stage{display:grid;grid-template-columns:minmax(0,1fr) minmax(430px,.56fr);gap:18px;align-items:start;margin-top:22px;}
.live .climbPane{min-width:0;}
.live .hero{border:1px solid var(--line);border-radius:16px;background:linear-gradient(180deg,var(--panel),var(--panel2));padding:18px 20px;}
.live .climb svg{width:100%;height:auto;display:block;}
.live .grid{stroke:var(--line);stroke-width:1;}.live .grid.base{stroke:#33405a;}
.live .axis,.live .gtick{fill:var(--muted);font-size:11px;font-family:ui-monospace,Menlo,monospace;}
.live .lReward{stroke:var(--brass);stroke-width:3;stroke-linejoin:round;stroke-linecap:round;}
.live .lSkill{stroke:var(--pos);stroke-width:2;stroke-dasharray:4 4;opacity:.85;}
.live .dot{fill:var(--brass);}.live .dot.kept{fill:var(--brass2);}
.live .promo{fill:var(--brass2);stroke:#1a130a;stroke-width:.5;}
.live .pulse{fill:var(--brass2);animation:pp 1.6s infinite;}
@keyframes pp{0%{r:5;opacity:1}70%{r:13;opacity:0}100%{opacity:0}}
.live .warm{fill:var(--muted);font-size:14px;font-style:italic;}
.live .foot{display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--muted);}
.live .lg{display:inline-flex;align-items:center;gap:6px;}
.live .sw{width:14px;height:3px;border-radius:2px;display:inline-block;}.live .sw.rw{background:var(--brass);}.live .sw.sk{background:var(--pos);}.live .sw.pr{width:8px;height:8px;border-radius:0;transform:rotate(45deg);background:var(--brass2);}
.live .note{margin-left:auto;font-style:italic;}
.live .vitals{display:grid;grid-template-columns:repeat(5,1fr);gap:0;margin-top:18px;border-top:1px solid var(--line);}
@media(max-width:720px){.live .vitals{grid-template-columns:repeat(2,1fr);}}
.live .vt{padding:14px 16px 4px;border-left:1px solid var(--line);}.live .vt:first-child{border-left:0;}
.live .vk{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:6px;}
.live .vv{font-family:ui-monospace,Menlo,monospace;font-size:24px;font-weight:500;}
.live .vv.brass{color:var(--brass2);}.live .vv.ok{color:var(--pos);}.live .vv.bad{color:var(--neg);}
.live .vsub{display:block;font-size:11.5px;color:var(--muted);margin-top:3px;}.live .vsub .up{color:var(--pos);}.live .vsub .dn{color:var(--neg);}
.live .transfer{margin-top:14px;border:1px solid rgba(79,209,168,.35);background:rgba(79,209,168,.07);border-radius:12px;padding:13px 17px;font-size:14px;line-height:1.5;}
.live .transfer .up{color:var(--pos);}.live .transfer .ok{color:var(--pos);}
.live .feedwrap{min-width:0;border:1px solid var(--line);border-radius:16px;background:linear-gradient(180deg,var(--panel),var(--panel2));padding:16px;max-height:calc(100vh - 188px);overflow:hidden;display:flex;flex-direction:column;}
.live .feedHead{display:flex;align-items:baseline;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:12px;}
.live .feedHead h3{font-family:Fraunces,Georgia,serif;font-weight:500;font-size:18px;margin:0;}
.live .feedHead span{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--muted);white-space:nowrap;}
.live .feed{display:flex;flex-direction:column;gap:12px;overflow-y:auto;min-height:0;padding-right:4px;}
.live .empty{color:var(--muted);font-size:13px;padding:24px;text-align:center;border:1px dashed var(--line);border-radius:12px;}
.live .spot{border:1px solid var(--line);border-radius:12px;background:rgba(20,23,31,.82);padding:13px 15px;}
.live .spot.latest{border-color:rgba(217,162,74,.48);box-shadow:0 0 0 1px rgba(217,162,74,.08),0 12px 34px rgba(0,0,0,.24);}
.live .spotHead{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:9px;}
.live .spotHead b{font-size:13.5px;}.live .spotHead span{font-size:11.5px;color:var(--muted);}
.live .talk{display:flex;flex-direction:column;gap:6px;}
.live .turn{display:flex;flex-direction:column;max-width:78%;}
.live .turn.seller{align-items:flex-start;}.live .turn.buyer{align-self:flex-end;align-items:flex-end;}
.live .who{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:0 4px 2px;}
.live .bubble{display:inline-flex;align-items:baseline;gap:9px;padding:7px 11px;border-radius:11px;font-size:13.5px;line-height:1.4;}
.live .turn.seller .bubble{background:rgba(110,168,255,.12);border:1px solid rgba(110,168,255,.25);border-bottom-left-radius:3px;}
.live .turn.buyer .bubble{background:rgba(224,168,90,.13);border:1px solid rgba(224,168,90,.28);border-bottom-right-radius:3px;}
.live .offer{font-family:ui-monospace,Menlo,monospace;font-weight:600;font-size:12px;color:var(--brass2);white-space:nowrap;}
.live .spotOut{margin-top:9px;font-size:12px;font-weight:600;font-family:ui-monospace,Menlo,monospace;}
.live .spotOut.deal{color:var(--pos);}.live .spotOut.nodeal{color:var(--muted);}
@media(max-width:1040px){.live .stage{grid-template-columns:1fr}.live .feedwrap{max-height:none;overflow:visible}.live .feed{overflow:visible}.live .ctrls{width:100%;}.live .btn{flex:1;text-align:center;}}
`;

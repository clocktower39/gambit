"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const BACKEND = process.env.NEXT_PUBLIC_AGUI_HTTP ?? "http://localhost:8000";

type Run = {
  run_id: string; ts: string; category: string; source: string | null; title: string;
  checkpoint: string | null; episodes: number; deals: number; mean_reward: number | null;
  viol: number; buckets: string[];
};
type Move = { role: "seller" | "buyer"; action?: string | null; offer: number | null; text: string };
type Outcome = { result: string; deal: boolean; price: number | null; reward: number | null; surplus: number | null; skill: number | null; viol: number; turns: number | null; bucket: string | null; gen: number | null };
type Reflection = { bucket: string | null; seller_lesson: string | null; buyer_lesson: string | null; surplus: number | null; viol: number };
type Detail = { run_id: string; title: string | null; moves: Move[]; outcomes: Outcome[]; reflections: Reflection[]; curve: { gen: number; reward: number }[]; spans?: number; error?: string };

const money = (v: number | null) => (v == null ? "—" : `$${Number.isInteger(v) ? v : v.toFixed(2)}`);
const num2 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));

const CAT_COLORS: Record<string, string> = {
  "self-play": "#6ea8ff", "offline-rl": "#4fd1a8", "human-vs-agent": "#e0a85a",
  reflection: "#9b8cff", negotiation: "#869c8b", harvest: "#e08a5b", overview: "#8b97a8", eval: "#9b8cff",
};
const catColor = (c: string) => CAT_COLORS[c] ?? "#8a909c";
const fmt = (ts: string) => { try { return new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); } catch { return ts; } };

// integrity (viol) signal — clean vs broken-rule
function Viol({ n }: { n: number }) {
  return <span className={`viol ${n === 0 ? "clean" : "bad"}`}>{n === 0 ? "clean" : `${n} viol`}</span>;
}

// reward-by-generation curve — the project's signature: a learning agent climbing
function Curve({ pts }: { pts: { gen: number; reward: number }[] }) {
  if (pts.length < 2) return null;
  const W = 460, H = 130, pad = 24;
  const maxG = Math.max(...pts.map((p) => p.gen), 1);
  const x = (g: number) => pad + (g / maxG) * (W - pad * 2);
  const y = (v: number) => H - pad - Math.max(0, Math.min(1, v)) * (H - pad * 2);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(p.gen).toFixed(1)},${y(p.reward).toFixed(1)}`).join(" ");
  const area = `${line} L${x(maxG).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  const first = pts[0].reward, last = pts[pts.length - 1].reward, delta = last - first;
  return (
    <div className="curveWrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="curve" role="img" aria-label="Mean reward by generation">
        <defs>
          <linearGradient id="rewardFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#d9a24a" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#d9a24a" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((v) => (
          <g key={v}>
            <line x1={pad} y1={y(v)} x2={W - pad} y2={y(v)} className="grid" />
            <text x={pad - 7} y={y(v) + 3} textAnchor="end" className="axislbl">{v}</text>
          </g>
        ))}
        <path d={area} className="areaReward" />
        <path d={line} className="lineReward" fill="none" />
        {pts.map((p, i) => (
          <circle key={p.gen} cx={x(p.gen)} cy={y(p.reward)} r={i === pts.length - 1 ? 4 : 3}
            className={`dotReward ${i === pts.length - 1 ? "last" : ""}`} />
        ))}
      </svg>
      <div className="curveDelta">
        gen 0 → {maxG}: reward {first.toFixed(2)} → {last.toFixed(2)}{" "}
        <b className={delta < 0 ? "down" : ""}>{delta >= 0 ? "+" : ""}{delta.toFixed(2)}</b>
      </div>
    </div>
  );
}

// episode outcomes as a table — only the columns the trace actually has
function OutcomeTable({ rows }: { rows: Outcome[] }) {
  const has = (k: keyof Outcome) => rows.some((o) => o[k] != null);
  const cols = {
    gen: has("gen"), reward: has("reward"), skill: has("skill"),
    surplus: has("surplus"), turns: has("turns"), bucket: has("bucket"),
  };
  const deals = rows.filter((o) => o.deal).length;
  const prices = rows.filter((o) => o.deal && o.price != null).map((o) => o.price as number);
  const avgPrice = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null;
  const totViol = rows.reduce((s, o) => s + (o.viol || 0), 0);
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
              {cols.gen && <th>gen</th>}
              <th>result</th>
              {cols.reward && <th>reward</th>}
              {cols.skill && <th>skill</th>}
              {cols.surplus && <th>surplus</th>}
              {cols.turns && <th>turns</th>}
              <th>viol</th>
              {cols.bucket && <th>bucket</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((o, i) => (
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
    </>
  );
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [configured, setConfigured] = useState(true);
  const [streamReady, setStreamReady] = useState(false);
  const [cat, setCat] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const reqRef = useRef(0);

  useEffect(() => {
    const es = new EventSource(`${BACKEND}/runs/stream`);
    es.onmessage = (e) => {
      let ev: any;
      try { ev = JSON.parse(e.data); } catch { return; }   // ignore malformed frames / keepalives
      if (ev.type !== "runs") return;
      setStreamReady(true);
      setConfigured(ev.configured);
      setRuns(ev.runs ?? []);
    };
    return () => es.close();
  }, []);

  const openRun = useCallback(async (rid: string) => {
    const my = ++reqRef.current;                            // guard against out-of-order responses
    setSelected(rid); setDetail(null); setDetailError(null); setLoadingDetail(true);
    try {
      const r = await fetch(`${BACKEND}/run?run_id=${encodeURIComponent(rid)}`);
      const j = await r.json().catch(() => ({ error: "bad response" }));
      if (reqRef.current !== my) return;                    // a newer click won
      if (!r.ok || j.error) setDetailError(j.retry || r.status === 429 ? "throttled" : (j.error || `error ${r.status}`));
      else setDetail(j);
    } catch {
      if (reqRef.current === my) setDetailError("offline");
    } finally {
      if (reqRef.current === my) setLoadingDetail(false);
    }
  }, []);

  const cats = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of runs) m[r.category] = (m[r.category] ?? 0) + 1;
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [runs]);

  // aggregate story across every run — the page's thesis
  const agg = useMemo(() => {
    const rewarded = runs.filter((r) => r.mean_reward != null);
    return {
      episodes: runs.reduce((s, r) => s + (r.episodes || 0), 0),
      deals: runs.reduce((s, r) => s + (r.deals || 0), 0),
      viol: runs.reduce((s, r) => s + (r.viol || 0), 0),
      reward: rewarded.length ? rewarded.reduce((s, r) => s + (r.mean_reward as number), 0) / rewarded.length : null,
    };
  }, [runs]);

  const shown = useMemo(() => {
    const ql = query.trim().toLowerCase();
    return runs.filter((r) =>
      (cat === "all" || r.category === cat) &&
      (!ql || r.title.toLowerCase().includes(ql) || (r.buckets || []).join(" ").toLowerCase().includes(ql) || (r.run_id || "").toLowerCase().includes(ql))
    );
  }, [runs, cat, query]);

  const selectedRun = useMemo(() => runs.find((r) => r.run_id === selected), [runs, selected]);

  return (
    <main className="runs">
      <header className="rHead">
        <div>
          <span className={`eyebrow tag ${configured ? "live" : "error"}`}>
            {configured ? "live · read from Logfire" : "no Logfire token configured"}
          </span>
          <h1>Run <em>history</em></h1>
          <p>Every match Gambit has played — self-play, offline-RL, your own haggling, and the lessons the Gemini optimizer wrote back — reconstructed from the trace.</p>
        </div>
        <Link href="/chat" className="chatLink">Haggle the agent <span className="arr">→</span></Link>
      </header>

      <section className="summary" aria-label="Totals across every run">
        <div className="stat"><span className="k">Runs</span><span className="v num">{runs.length}</span></div>
        <div className="stat"><span className="k">Episodes played</span><span className="v num">{agg.episodes.toLocaleString()}</span></div>
        <div className="stat"><span className="k">Deals closed</span><span className="v num">{agg.deals.toLocaleString()}</span></div>
        <div className="stat"><span className="k">Mean reward</span><span className="v num brass">{agg.reward == null ? "—" : agg.reward.toFixed(2)}</span></div>
        <div className="stat"><span className="k">Integrity breaks</span><span className={`v num ${agg.viol === 0 ? "pos" : "neg"}`}>{agg.viol}</span></div>
      </section>

      <div className="filters">
        <button className={`chip all-chip ${cat === "all" ? "on" : ""}`} onClick={() => setCat("all")}>
          <span className="cdot" />all <b>{runs.length}</b>
        </button>
        {cats.map(([c, n]) => (
          <button key={c} className={`chip ${cat === c ? "on" : ""}`} onClick={() => setCat(c)} style={{ ["--c" as any]: catColor(c) }}>
            <span className="cdot" />{c} <b>{n}</b>
          </button>
        ))}
        <input className="search" placeholder="Search title, bucket, or run id…" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>

      <div className="browser">
        <div className="runlist">
          {!streamReady && shown.length === 0 && [0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="skRow"><span className="skel l1" /><span className="skel l2" /></div>
          ))}
          {streamReady && shown.length === 0 && (
            <div className="empty">
              <span className="glyph">{searchGlyph}</span>
              <span className="lead">{runs.length ? "Nothing matches" : "No runs yet"}</span>
              <span className="hint">{runs.length ? "Try a different category or clear the search." : "Runs appear here as Gambit plays them."}</span>
            </div>
          )}
          {shown.map((r) => (
            <button key={r.run_id} className={`runrow ${selected === r.run_id ? "sel" : ""}`} onClick={() => openRun(r.run_id)} style={{ ["--c" as any]: catColor(r.category) }}>
              <span className="rtop">
                <span className="cbadge">{r.category}</span>
                <span className="rtitle">{r.title}{r.source === "human" && <span className="srcdot"> · you</span>}</span>
              </span>
              <span className="rtime">{fmt(r.ts)}</span>
              <span className="rmeta">
                {r.episodes > 0 && <>{r.episodes} ep</>}
                {r.deals > 0 && <><span className="sep">·</span>{r.deals} deal{r.deals > 1 ? "s" : ""}</>}
                {r.mean_reward != null && <><span className="sep">·</span><span className="reward-v">reward {r.mean_reward.toFixed(2)}</span></>}
                <span className="sep">·</span><Viol n={r.viol} />
                {r.buckets?.slice(0, 3).map((b) => <span key={b} className="btag">{b}</span>)}
              </span>
            </button>
          ))}
        </div>

        <div className="detail">
          {!selected && (
            <div className="empty">
              <span className="glyph">{curveGlyph}</span>
              <span className="lead">Pick a run to replay it</span>
              <span className="hint">You'll see how reward climbed, every offer traded, and what the optimizer learned.</span>
            </div>
          )}
          {selected && loadingDetail && (
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
          {selected && !loadingDetail && detailError && (
            <div className="empty err">
              <span className="glyph">{warnGlyph}</span>
              <span className="lead">
                {detailError === "throttled" ? "Logfire is rate-limited" : detailError === "offline" ? "Can't reach the backend" : detailError}
              </span>
              <span className="hint">
                {detailError === "throttled" ? "Give it a few seconds, then open the run again."
                  : detailError === "offline" ? "The trace service isn't responding. Check it's running, then retry."
                  : "Something went wrong loading this run."}
              </span>
            </div>
          )}
          {detail && (
            <>
              {(detail.title || selectedRun) && (
                <header className="dhead">
                  <h2 className="dtitle">{detail.title ?? selectedRun?.title}</h2>
                  {selectedRun && (
                    <p className="dsub">
                      <span>{selectedRun.category}</span>
                      <span className="sep">·</span><span>{fmt(selectedRun.ts)}</span>
                      {selectedRun.checkpoint && <><span className="sep">·</span><span>{selectedRun.checkpoint}</span></>}
                    </p>
                  )}
                </header>
              )}
              {detail.curve.length > 1 && (
                <section className="dsec">
                  <h3>Reward by generation <span className="sub">{detail.curve.length} gens</span></h3>
                  <Curve pts={detail.curve} />
                </section>
              )}
              {detail.outcomes.length > 1 && (
                <section className="dsec">
                  <h3>Episodes <span className="sub">{detail.outcomes.length}</span></h3>
                  <OutcomeTable rows={detail.outcomes} />
                </section>
              )}
              {detail.moves.length > 0 && (
                <section className="dsec">
                  <h3>Transcript <span className="sub">{detail.moves.length} turns</span></h3>
                  <div className="talk">
                    {detail.moves.map((m, i) => (
                      <div key={i} className={`turn ${m.role}`}>
                        <span className="who">{m.role}</span>
                        <div className="bubble">
                          <span className="say">{m.text || (m.action ? `(${m.action})` : "")}</span>
                          {m.offer != null && <span className="offer">{money(m.offer)}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                  {detail.outcomes.length === 1 && (
                    <div className={`epOut ${detail.outcomes[0].deal ? "deal" : "nodeal"}`}>
                      {detail.outcomes[0].deal ? (
                        <>
                          <span className="lead">Deal</span>
                          {money(detail.outcomes[0].price)}
                          <span>reward {num2(detail.outcomes[0].reward)}</span>
                          <span>skill {num2(detail.outcomes[0].skill)}</span>
                          {detail.outcomes[0].surplus != null && <span>surplus {num2(detail.outcomes[0].surplus)}</span>}
                          {detail.outcomes[0].turns != null && <span>{detail.outcomes[0].turns} turns</span>}
                        </>
                      ) : (
                        <><span className="lead">No deal</span><span>{detail.outcomes[0].result}</span></>
                      )}
                    </div>
                  )}
                </section>
              )}
              {detail.reflections.length > 0 && (
                <section className="dsec gemini">
                  <h3>What the Gemini optimizer learned <span className="sub">{detail.reflections.length}</span></h3>
                  {detail.reflections.map((r, i) => (
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
              {detail.moves.length === 0 && detail.outcomes.length === 0 && detail.reflections.length === 0 && (
                <div className="empty">
                  <span className="glyph">{metricsGlyph}</span>
                  <span className="lead">Metrics only</span>
                  <span className="hint">This run traced numbers, not a transcript{detail.spans ? ` (${detail.spans} spans)` : ""}. Negotiation and human-play runs show the full exchange; reflection runs show the lessons.</span>
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
  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
  </svg>
);
const curveGlyph = (
  <svg width="42" height="42" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 38h36" opacity="0.5" />
    <path d="M8 34c6-1 9-9 14-14s9-9 18-12" />
    <circle cx="40" cy="8" r="2.5" fill="currentColor" stroke="none" />
  </svg>
);
const warnGlyph = (
  <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4" /><circle cx="12" cy="17" r="0.6" fill="currentColor" />
  </svg>
);
const metricsGlyph = (
  <svg width="40" height="40" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M8 40V20M20 40V10M32 40V26M44 40V16" /><path d="M4 40h40" opacity="0.5" />
  </svg>
);

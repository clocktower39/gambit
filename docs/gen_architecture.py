"""Generates docs/architecture.excalidraw — the Gambit system architecture.

Edit this script and re-run (`python docs/gen_architecture.py`) to tweak the diagram,
or just open the .excalidraw file in excalidraw.com / the VS Code Excalidraw extension
and drag things around directly.
"""

import itertools
import json
import os

elements = []
_id = itertools.count(1)
_seed = itertools.count(1)


def nid(p):
    return f"{p}{next(_id)}"


def seed():
    return next(_seed) * 1000 + 7


# Sponsor / role color palette: (fill, stroke)
C = {
    "do":      ("#dbeafe", "#1d4ed8"),  # DigitalOcean — blue
    "livekit": ("#ccfbf1", "#0d9488"),  # LiveKit — teal
    "gemini":  ("#ede9fe", "#7c3aed"),  # Gemini — purple
    "loop":    ("#fef3c7", "#d97706"),  # continual-learning core — amber
    "real":    ("#dcfce7", "#16a34a"),  # real marketplace — green
    "gray":    ("#f1f5f9", "#475569"),  # our plumbing — neutral
}


def base(**kw):
    d = dict(
        angle=0, strokeColor="#1e1e1e", backgroundColor="transparent",
        fillStyle="solid", strokeWidth=2, strokeStyle="solid", roughness=1,
        opacity=100, groupIds=[], frameId=None, roundness=None, seed=seed(),
        version=1, versionNonce=seed(), isDeleted=False, boundElements=[],
        updated=1, link=None, locked=False,
    )
    d.update(kw)
    return d


def text(s, x, y, size=14, color="#1e1e1e", align="left", w=None):
    lines = s.split("\n")
    tw = w if w else max(len(l) for l in lines) * size * 0.58
    th = len(lines) * size * 1.25
    elements.append(base(
        id=nid("t"), type="text", x=x, y=y, width=tw, height=th,
        strokeColor=color, text=s, fontSize=size, fontFamily=2,
        textAlign=align, verticalAlign="top", containerId=None,
        originalText=s, lineHeight=1.25, baseline=round(size * 0.8),
    ))


def box(x, y, w, h, label, role="gray", size=14, dashed=False):
    fill, stroke = C[role]
    elements.append(base(
        id=nid("r"), type="rectangle", x=x, y=y, width=w, height=h,
        backgroundColor=fill, strokeColor=stroke, roundness={"type": 3},
        strokeStyle="dashed" if dashed else "solid",
    ))
    if label:
        lines = label.split("\n")
        tw = max(len(l) for l in lines) * size * 0.55
        th = len(lines) * size * 1.25
        text(label, x + (w - tw) / 2, y + (h - th) / 2, size=size,
             color="#0f172a", align="center", w=tw)
    return (x, y, w, h)


def arrow(pts, color="#475569", dashed=False, width=2, label=None):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = pts[0]
    elements.append(base(
        id=nid("a"), type="arrow", x=x0, y=y0,
        width=max(xs) - min(xs), height=max(ys) - min(ys),
        strokeColor=color, strokeStyle="dashed" if dashed else "solid",
        strokeWidth=width, points=[[p[0] - x0, p[1] - y0] for p in pts],
        lastCommittedPoint=None, startBinding=None, endBinding=None,
        startArrowhead=None, endArrowhead="arrow", roundness={"type": 2},
    ))
    if label:
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        text(label, mx - len(label) * 3, my - 16, size=11, color=color, align="center")


def edge(p1, p2, **kw):
    arrow([p1, p2], **kw)


def bottom(b):
    return (b[0] + b[2] / 2, b[1] + b[3])


def top(b):
    return (b[0] + b[2] / 2, b[1])


def left(b):
    return (b[0], b[1] + b[3] / 2)


def right(b):
    return (b[0] + b[2], b[1] + b[3] / 2)


# ---- Title ---------------------------------------------------------------
text("Gambit — Self-Improving Auto-Negotiator", 60, 24, size=30, color="#0f172a")
text("Theme: Continual Learning.  ONE negotiation policy — used in production (left) "
     "and trained by a self-improvement loop (right).", 60, 66, size=15, color="#475569")

# ---- Legend --------------------------------------------------------------
lx = 1010
text("LEGEND", lx, 20, size=13, color="#0f172a")
legend = [("DigitalOcean", "do"), ("LiveKit", "livekit"), ("Gemini", "gemini"),
          ("Learning core", "loop"), ("Real marketplace", "real"), ("Our code", "gray")]
for i, (name, role) in enumerate(legend):
    yy = 44 + i * 26
    box(lx, yy, 18, 18, "", role=role)
    text(name, lx + 26, yy + 1, size=12, color="#475569")

# ===== HUB (the shared brain) =============================================
hub = box(560, 330, 360, 120,
          "🤝  NEGOTIATOR AGENT\nDigitalOcean Serverless Inference\nacts on its current Strategy",
          role="loop", size=15)
strat = box(560, 470, 360, 80,
            "🧠  Strategy (tactics + knobs)  +  Memory\npgvector on DO Postgres — recalls past deals",
            role="do", size=13)
edge(top(strat), bottom(hub), color="#1d4ed8", label="informs")

# ===== LEFT WING — production path ========================================
text("PRODUCTION PATH  (real selling)", 60, 110, size=16, color="#0f172a")
l1 = box(60, 140, 300, 52, "🎙️  Voice intake  (LiveKit)\nseller describes the item out loud", role="livekit", size=12)
l2 = box(60, 205, 300, 52, "📸  Photo → listing image\nDO image gen (gpt-image / SD-3.5 / flux)", role="do", size=12)
l3 = box(60, 270, 300, 50, "💲  Price inputs:  min · target · max\n(floor price stays secret)", role="gray", size=12)
l4 = box(60, 335, 300, 44, "📦  Listing  (Item object)", role="gray", size=13)
l5 = box(60, 398, 300, 44, "🔌  Connector interface", role="gray", size=13)
l6 = box(60, 460, 300, 62, "🟢  eBay Sandbox\nreal listing + Best Offer / Negotiation API", role="real", size=12)
l7 = box(60, 538, 300, 62, "🖥️  Gemini computer-use auto-post\nfor sites with no API", role="gemini", size=12)
l8 = box(60, 616, 300, 46, "🧑  Real buyers — offers & messages", role="gray", size=13)

edge(bottom(l1), top(l2))
edge(bottom(l2), top(l3))
edge(bottom(l3), top(l4))
edge(bottom(l4), top(l5))
edge(bottom(l5), top(l6))
edge(bottom(l6), top(l7), dashed=True)
edge(bottom(l7), top(l8))
arrow([right(l8), (480, 639), (480, 410), left(hub)], color="#16a34a", width=3, label="negotiate")

# ===== RIGHT WING — self-improvement loop ★ ================================
text("SELF-IMPROVEMENT LOOP  ★ centerpiece", 1010, 110, size=16, color="#b45309")
r1 = box(1010, 200, 340, 64, "🧪  Buyer Simulator\npersonas + hidden reservation price", role="gray", size=12)
r2 = box(1010, 286, 340, 44, "💬  Episodes — transcripts + outcomes", role="loop", size=13)
r3 = box(1010, 354, 340, 60, "📊  Score:  surplus capture · close rate · turns\n+ LLM-as-judge (DO)", role="loop", size=12)
r4 = box(1010, 438, 340, 60, "🪞  Optimizer — reflect on transcripts →\npropose an improved Strategy", role="loop", size=12)
r5 = box(1010, 522, 340, 48, "⚖️  A/B select — keep better → next generation", role="loop", size=12)
r6 = box(1010, 594, 340, 60, "🔥  (stretch) Gemma 4 LoRA fine-tune\non winning transcripts · DO GPU", role="gemini", size=12, dashed=True)

arrow([right(hub), (965, 390), (965, 232), left(r1)], color="#d97706", width=3, label="negotiate")
edge(bottom(r1), top(r2))
edge(bottom(r2), top(r3))
edge(bottom(r3), top(r4))
edge(bottom(r4), top(r5))
arrow([left(r5), (965, 546), (965, 510), right(strat)], color="#d97706", width=3, label="deploy improved strategy  ↺")
arrow([(1180, 330), (1180, 594)], color="#7c3aed", dashed=True, label="winning transcripts")
arrow([left(r6), (940, 625), (940, 400), bottom(hub)], color="#7c3aed", dashed=True, label="improved weights")
arrow([left(r2), (935, 308), (935, 505), right(strat)], color="#1d4ed8", dashed=True, label="store")

# ===== BOTTOM — surfaces & infra ==========================================
text("SURFACES & INFRA  (DigitalOcean)", 60, 720, size=16, color="#0f172a")
i1 = box(60, 752, 250, 56, "🖥️  Live demo UI\nimprovement curve · feed", role="do", size=12)
i2 = box(330, 752, 250, 56, "📈  gen-0 vs gen-N\nhead-to-head (money shot)", role="loop", size=12)
box(600, 752, 230, 56, "☁️  DO App Platform\n(deploy)", role="do", size=12)
box(850, 752, 220, 56, "🪣  DO Spaces\n(images)", role="do", size=12)
box(1090, 752, 260, 56, "🐘  DO Postgres + pgvector\n(memory + run history)", role="do", size=12)
arrow([(1180, 570), (1180, 690), (185, 690), top(i1)], color="#1d4ed8", dashed=True, label="metrics")
edge(bottom(strat), top(i2), color="#d97706", dashed=True)

# ---- write ----------------------------------------------------------------
doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "gambit-architecture",
    "elements": elements,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}
out = os.path.join(os.path.dirname(__file__), "architecture.excalidraw")
with open(out, "w") as f:
    json.dump(doc, f, indent=2)
print(f"wrote {out}  ({len(elements)} elements)")

#!/usr/bin/env python3
"""Validate the 5 asset JSON files, generate round-trippable CSVs, and the markdown section."""
import json, csv, os

BASE = "/Users/jeanjimenez/JJJ/ai-negotiator/playbook"
JSON_DIR = os.path.join(BASE, "assets", "json")
CSV_DIR = os.path.join(BASE, "assets", "csv")
MD_PATH = os.path.join(BASE, "SECTION-7-reusable-assets.md")

SEP = "; "

def flat(v):
    """Flatten a value for CSV. Lists -> '; ' joined. Dicts -> k=v pairs joined."""
    if v is None:
        return ""
    if isinstance(v, list):
        return SEP.join(flat(x) for x in v)
    if isinstance(v, dict):
        return SEP.join(f"{k}={flat(val)}" for k, val in v.items())
    return str(v)

def load(name):
    with open(os.path.join(JSON_DIR, name)) as f:
        return json.load(f)

# ---- load + validate all JSON ----
principles = load("principles.json")
intents = load("buyer-intent-classifier.json")
objections = load("objection-library.json")
concessions = load("concession-table.json")
coaching = load("coaching-tips.json")
print("All 5 JSON files parsed OK.")

# ---- CSV generation ----
def write_csv(filename, rows, fields):
    path = os.path.join(CSV_DIR, filename)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: flat(r.get(k)) for k in fields})
    print(f"  wrote {filename} ({len(rows)} rows)")

# principles
p_fields = ["id","name","one_line","why_it_works","when_to_use","when_not_to_use",
            "marketplace_surface","product_stage_tags","source_books","primary_source",
            "marketplace_fit_rank","example_buyer_message","recommended_reply","conflict_notes"]
write_csv("principles.csv", principles["principles"], p_fields)

# buyer-intent-classifier
i_fields = ["id","label","description","observable_signals","likely_underlying_interest",
            "recommended_strategy","risk_flags","source_books"]
write_csv("buyer-intent-classifier.csv", intents["intents"], i_fields)

# objection-library (sample_replies is a dict)
o_fields = ["id","objection_key","buyer_says","what_they_really_mean","recommended_approach",
            "principles_used","sample_replies","escalate_or_disengage_if","source_books"]
write_csv("objection-library.csv", objections["objections"], o_fields)

# concession-table
c_fields = ["id","scenario","recommended_response","concession_mechanic","hold_firm_conditions",
            "non_monetary_alternatives","max_discount_guidance","source_books"]
write_csv("concession-table.csv", concessions["concessions"], c_fields)

# coaching-tips
ch_fields = ["id","tip","seller_mistake_it_corrects","why","how_the_copilot_applies_it","source_books"]
write_csv("coaching-tips.csv", coaching["tips"], ch_fields)

# ---- round-trip check: read CSV back, confirm row counts + id match ----
def roundtrip(filename, src_rows, id_key="id"):
    path = os.path.join(CSV_DIR, filename)
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(src_rows), f"{filename} row count mismatch"
    for a, b in zip(rows, src_rows):
        assert a[id_key] == b[id_key], f"{filename} id mismatch {a[id_key]} != {b[id_key]}"
    print(f"  round-trip OK: {filename}")

roundtrip("principles.csv", principles["principles"])
roundtrip("buyer-intent-classifier.csv", intents["intents"])
roundtrip("objection-library.csv", objections["objections"])
roundtrip("concession-table.csv", concessions["concessions"])
roundtrip("coaching-tips.csv", coaching["tips"])

# ---- Markdown generation ----
def md_escape(s):
    return str(s).replace("|", "\\|").replace("\n", " ").strip()

def md_cell(v):
    return md_escape(flat(v))

def md_table(headers, rows, keys):
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for r in rows:
        out.append("| " + " | ".join(md_cell(r.get(k)) for k in keys) + " |")
    return "\n".join(out)

lines = []
lines.append("# Section 7 — Canonical Reusable Product Assets\n")
lines.append("Pass-2 cross-source synthesis of the 7 Pass-1 book profiles into 5 stable-keyed assets that drop directly into the selling-copilot's config/rules. Every row cites its source books; synthesized/inferred content is flagged inline. The machine-readable source of truth is `assets/json/`; flattened CSVs (arrays joined with `; `) live in `assets/csv/`.\n")

bookkey = principles["source_books_key"]
lines.append("**Source-book codes:** " + SEP.join(f"`{k}` = {v}" for k, v in bookkey.items()) + "\n")

# 1 principles
lines.append("## 1. Principles Table (PRIN-xxx)\n")
lines.append(f"{len(principles['principles'])} canonical principles deduplicated from the 111 plays, ranked by P2P-marketplace fit (5 = highest). Conflicts are noted in the final column.\n")
lines.append(md_table(
    ["ID","Name","One-line","Fit","Marketplace surface","Stage tags","Sources","Primary","Conflict / reconciliation"],
    principles["principles"],
    ["id","name","one_line","marketplace_fit_rank","marketplace_surface","product_stage_tags","source_books","primary_source","conflict_notes"]))
lines.append("")
lines.append("### Example messages & replies\n")
lines.append(md_table(
    ["ID","Name","Example buyer message","Recommended reply"],
    principles["principles"],
    ["id","name","example_buyer_message","recommended_reply"]))
lines.append("")

# 2 intents
lines.append("## 2. Buyer-Intent Classifier (INTENT-xxx)\n")
lines.append(f"{len(intents['intents'])} buyer intent/type categories the copilot detects from a message, with concrete observable signals and the PRIN ids to deploy.\n")
lines.append(md_table(
    ["ID","Label","Observable signals","Likely interest","Recommended strategy (PRIN)","Risk flags","Sources"],
    intents["intents"],
    ["id","label","observable_signals","likely_underlying_interest","recommended_strategy","risk_flags","source_books"]))
lines.append("")

# 3 objections
lines.append("## 3. Objection Library (OBJ-<key>)\n")
lines.append(f"{len(objections['objections'])} objection handlers keyed by the standard taxonomy, each with warm / firm / data-backed reply variations.\n")
lines.append(md_table(
    ["ID","Buyer says","What they really mean","Approach","Principles","Escalate / disengage if","Sources"],
    objections["objections"],
    ["id","buyer_says","what_they_really_mean","recommended_approach","principles_used","escalate_or_disengage_if","source_books"]))
lines.append("")
lines.append("### Sample replies (warm / firm / data-backed)\n")
for o in objections["objections"]:
    sr = o["sample_replies"]
    lines.append(f"**{o['id']}**  ")
    lines.append(f"- _warm_: {md_escape(sr['warm'])}  ")
    lines.append(f"- _firm_: {md_escape(sr['firm'])}  ")
    lines.append(f"- _data-backed_: {md_escape(sr['data_backed'])}  ")
    lines.append("")

# 4 concessions
lines.append("## 4. Concession Strategy Table (CONC-xxx)\n")
lines.append(f"{len(concessions['concessions'])} concession policies for casual sellers. Max-discount figures are synthesized defaults (the books supply logic, not percentages) and should be overridden by the seller's real floor/BATNA.\n")
lines.append(md_table(
    ["ID","Scenario","Recommended response","Concession mechanic","Hold-firm conditions","Non-monetary alternatives","Max-discount guidance","Sources"],
    concessions["concessions"],
    ["id","scenario","recommended_response","concession_mechanic","hold_firm_conditions","non_monetary_alternatives","max_discount_guidance","source_books"]))
lines.append("")

# 5 coaching
lines.append("## 5. Seller Coaching Tips (COACH-xxx)\n")
lines.append(f"{len(coaching['tips'])} seller-side coaching tips from all books' seller_psychology, each mapped to the copilot's automated nudge / suggestion / guardrail.\n")
lines.append(md_table(
    ["ID","Tip","Mistake it corrects","Why","How the copilot applies it","Sources"],
    coaching["tips"],
    ["id","tip","seller_mistake_it_corrects","why","how_the_copilot_applies_it","source_books"]))
lines.append("")

with open(MD_PATH, "w") as f:
    f.write("\n".join(lines))
print(f"Wrote markdown: {MD_PATH}")
print("DONE.")

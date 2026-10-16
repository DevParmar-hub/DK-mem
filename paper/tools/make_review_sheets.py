"""Native-review sheets (CSV, open in Excel/Sheets), one per language, plus bank and lexicon sheets for Marathi/Gujarati.

    python paper/tools/make_review_sheets.py            # writes paper/review/*_review.csv (refuses to overwrite a filled sheet)

* hi_pairs_review.csv  -- the 63 Hindi pairs ACTUALLY EVALUATED in the paper (v1.0 arm; from eval/tier2/data), so a flagged pair can be
                          dropped in the sensitivity table (paper/tools/make_numbers.py --exclude).
* mr/gu_pairs_review.csv -- the Marathi/Gujarati specs of the v2.1 dev package (NOT evaluated in the paper; reviewed for the benchmark release).
  Rows repaired by the assistant carry repaired=yes and the reason: review those first.
* mr/gu_bank_review.csv, mr/gu_lexicon_review.csv -- distractor turns and proposed lexicon entries.

Reviewers fill only the empty columns. Sheets carry dev labels (already exposed) and no test label; keep the repo PRIVATE.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "paper" / "review"
PAIR_COLS = ["verdict(correct/wrong/ambiguous)", "natural(yes/awkward/no)", "class_ok(yes/no)", "comment"]


def _jl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def write(name, header, rows):
    p = OUT / name
    if p.exists():
        with open(p, encoding="utf-8-sig", newline="") as fh:
            filled = any(any(r.get(c, "").strip() for c in header if c in PAIR_COLS + ["verdict(ok/wrong/unsure)", "comment"]) for r in csv.DictReader(fh))
        if filled:
            print(f"kept {p.name} (already has reviewer input)")
            return
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:          # utf-8-sig: Excel shows Devanagari/Gujarati correctly
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print("wrote", p.relative_to(REPO), f"({len(rows)} rows)")


def hindi_rows():
    data = REPO / "eval" / "tier2" / "data"
    text = {t["turn_id"]: t["text"] for c in _jl(data / "tier2_conversations.jsonl") for s in c["sessions"] for t in s["turns"]}
    gold = {g["eval_pair_id"]: g for g in _jl(data / "tier2_gold.jsonl")}
    rows = []
    for m in sorted(_jl(data / "tier2_injection_metadata.jsonl"), key=lambda m: m["injected_pair_id"]):
        g = gold[m["injected_pair_id"]]
        if g["language"] != "hi":
            continue
        rows.append([m["injected_pair_id"], m["spec_id"], g["distinction_class"], g["relation"], text[m["turn_id_a"]], text[m["turn_id_b"]],
                     m["marker_a"], m["marker_b"], "", "", "", ""])
    return rows


def v21_rows(lang):
    pkg = REPO / "data" / "tier2_v2_1"
    specs = json.loads((pkg / "dev" / "pair_specs_v2_1.json").read_text(encoding="utf-8"))["specs"]
    rows = []
    for s in specs:
        if s["language"] != lang:
            continue
        rep = s.get("repair") or {}
        rows.append([s["spec_id"], s["distinction_class"], s["relation"], s["text_a"], s["text_b"], s["marker_a"], s["marker_b"],
                     "yes" if rep else "no", rep.get("reason", ""), rep.get("linguistic_confidence", ""), "", "", "", ""])
    return sorted(rows, key=lambda r: (r[7] != "yes", r[0]))          # repaired rows first


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    write("hi_pairs_review.csv", ["injected_pair_id", "spec_id", "class", "gold_relation", "text_a", "text_b", "marker_a", "marker_b", *PAIR_COLS], hindi_rows())
    pkg = REPO / "data" / "tier2_v2_1"
    if not (pkg / "dev" / "pair_specs_v2_1.json").exists():
        print("data/tier2_v2_1 absent: Marathi/Gujarati sheets not written (get the package from the lead)")
        return 0
    bank = json.loads((pkg / "banks" / "distractors_v2_1.json").read_text(encoding="utf-8"))
    lex_path = REPO / "data" / "team_b_delivery" / "member3_lexicon_proposal" / "proposed_distinction_features.json"
    lex = json.loads(lex_path.read_text(encoding="utf-8"))["entries"] if lex_path.exists() else []
    for lang in ("mr", "gu"):
        write(f"{lang}_pairs_review.csv", ["spec_id", "class", "gold_relation", "text_a", "text_b", "marker_a", "marker_b", "repaired", "repair_reason",
                                           "repair_confidence", *PAIR_COLS], v21_rows(lang))
        write(f"{lang}_bank_review.csv", ["index", "distractor_user_turn", "verdict(ok/wrong/unsure)", "comment"],
              [[i, t, "", ""] for i, t in enumerate(bank["user_turns"][lang])])
        write(f"{lang}_lexicon_review.csv", ["id", "class", "value", "match_type", "surface_forms", "notes", "verdict(ok/wrong/unsure)", "comment"],
              [[e["id"], e["distinction_class"], e["value"], e["match_type"], " | ".join(e["surface_forms"]), e.get("notes", ""), "", ""]
               for e in lex if e["lang"] == lang])
    return 0


if __name__ == "__main__":
    sys.exit(main())

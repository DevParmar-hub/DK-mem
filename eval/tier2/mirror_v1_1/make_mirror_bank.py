"""Write banks/pair_specs_mirror.json: the v1.1m counter-confound replacement sentence for member b of every v1.0 pair spec.

EVALUATOR side (reads the v1.0 pair specs; writes a bank that is as protected as they are). Deterministic; the output is the
hand-reviewable artifact the generator reads, and it is pinned by FROZEN_v1.1m.json. Refuses to overwrite.

Why. In v1.0 the attribute pattern alone predicts the gold relation: all 42 gold-different pairs give both members the SAME attribute
with different values (city/city, weekday/weekday), all 27 gold-same pairs give them DIFFERENT attributes (birthday + city, place +
weekday). A merge judge that keeps conflicting values apart and merges compatible facts scores perfectly on v1.0 without resolving
identity. The mirror arm flips the pattern and changes nothing else:

  gold different -> member b states a DIFFERENT attribute (same marker, same person reference)       42 pairs
  gold same      -> member b states the SAME attribute as member a with a CONFLICTING value (same marker)  27 pairs

Member a's sentence, both markers, the relation, the class, the language, the session positions and the distractors are unchanged
(the generator copies the v1.0 conversation). Values come from the v1.0 vocabulary (its cities, months and weekdays) so that no new
value is a cue. The six German register sentences are written out by hand (no template covers them).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1_SPECS = HERE.parent / "banks" / "pair_specs.json"
OUT = HERE / "banks" / "pair_specs_mirror.json"

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
CITIES = ["Pune", "Jaipur", "Delhi", "Lucknow", "Chennai", "Indore", "Nagpur", "Surat", "Kolkata", "Bhopal"]
PLURAL_HONORIFIC = ("dadi", "nani")          # v1.0 writes "aa rahi hain" for these two

# German honorific_register (gold different): member b keeps its Sie marker and states a different attribute than member a.
GERMAN = {
    "t2s_t1_0196": ("Chefin, können Sie mir die Unterlagen nach Leipzig schicken", {"attribute": "send_city", "value": "Leipzig"}),
    "t2s_t1_0197": ("Lena, haben Sie im Oktober Geburtstag", {"attribute": "birthday_month", "value": "Oktober"}),
    "t2s_t1_0198": ("Thomas, danke für Ihre Hilfe am Samstag", {"attribute": "help_weekday", "value": "Samstag"}),
    "t2s_t1_0200": ("Markus, wie war Ihr Urlaub im August", {"attribute": "holiday_month", "value": "August"}),
    "t2s_t1_0201": ("Sabine, Sie haben die Präsentation in Frankfurt super gemacht", {"attribute": "presentation_city", "value": "Frankfurt"}),
    "t2s_t1_0202": ("Jonas, können Sie mich am Donnerstag vom Bahnhof abholen", {"attribute": "pickup_weekday", "value": "Donnerstag"}),
}
# Hindi honorific_register (gold same): member b keeps its register marker and states member a's attribute (a city) with another value.
HINDI_REGISTER = {
    "t2s_t1_0187": "Maa, aap {c} se aa rahi hain",
    "t2s_t1_0188": "Papa, aap {c} se wapas aa rahe hain",
    "t2s_t1_0189": "Maa, tum {c} mein rehti ho",
    "t2s_t1_0191": "Nani, aap {c} mein hain",
    "t2s_t1_0192": "Papa, aap {c} ja rahe hain",
    "t2s_t1_0193": "Papa, aapne {c} mein mera result dekha",
    "t2s_t1_0194": "Maa, aapne {c} mein khana khaya",
}


def _other(values: list[str], avoid: str, k: int) -> str:
    pool = [v for v in values if v.casefold() != avoid.casefold()]
    return pool[k % len(pool)]


def mirror(spec: dict, k: int) -> dict:
    cls, rel, fa, mb = spec["distinction_class"], spec["relation"], spec["fact_a"], spec["marker_b"]
    if rel == "different":
        if cls == "honorific_register":
            text, fact = GERMAN[spec["spec_id"]]
        elif fa["attribute"] in ("residence_city", "visit_city"):
            m = MONTHS[k % 12]
            text, fact = f"Meri {mb} ka birthday {m} mein hai", {"attribute": "birthday_month", "value": m}
        elif fa["attribute"] == "call_weekday":
            c = CITIES[k % len(CITIES)]
            verb = "rehti hain" if mb in PLURAL_HONORIFIC else "rehti hai"
            text, fact = f"Meri {mb} {c} mein {verb}", {"attribute": "residence_city", "value": c}
        else:
            raise ValueError(f"no mirror rule for {spec['spec_id']}")
        if fact["attribute"] == fa["attribute"]:
            raise ValueError(f"{spec['spec_id']}: a gold-different mirror must change the attribute")
        pattern = "different_attribute"
    else:
        if cls == "name_variant":
            m = _other(MONTHS, fa["value"], k)
            text, fact = f"{mb} ka birthday {m} mein hai", {"attribute": fa["attribute"], "value": m}
        elif cls == "honorific_register":
            c = _other(CITIES, fa["value"], k)
            text, fact = HINDI_REGISTER[spec["spec_id"]].format(c=c), {"attribute": fa["attribute"], "value": c}
        else:
            raise ValueError(f"no mirror rule for {spec['spec_id']}")
        if fact["value"].casefold() == fa["value"].casefold():
            raise ValueError(f"{spec['spec_id']}: a gold-same mirror must conflict")
        pattern = "same_attribute_conflicting_value"
    if mb.split()[-1] not in text:
        raise ValueError(f"{spec['spec_id']}: the mirror sentence lost member b's marker {mb!r}")
    return {"spec_id": spec["spec_id"], "relation": rel, "distinction_class": cls, "language": spec["language"],
            "text_b": text, "fact_b": fact, "marker_b": mb, "attribute_pattern": pattern,
            "v1_0_attribute_pattern": "same_attribute" if spec["fact_b"]["attribute"] == fa["attribute"] else "different_attribute"}


def build() -> dict:
    specs = json.loads(V1_SPECS.read_text(encoding="utf-8"))["specs"]
    return {"spec_version": "1.1m", "description": __doc__.split("\n\n")[1].strip(),
            "specs": [mirror(s, k) for k, s in enumerate(specs)]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite {a.out}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

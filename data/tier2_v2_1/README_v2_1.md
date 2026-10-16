# Tier-2 v2.1 repair package (DRAFT, not frozen, not native-reviewed)

Derived by `eval/tier2/repair_v2_1.py` from Team B's v2.0-draft (`data/team_b_delivery/`, untouched; source specs sha256 in
`dev/pair_specs_v2_1.json:derived_from_sha256`). Rebuild: `python -m tier2.repair_v2_1 --out <empty dir>`.

## dev/  (126 specs, all split = dev)
- 18 specs repaired (see `CHANGELOG_v2_1.json`: before/after, reason, linguistic confidence, `needs_native_review`). Gold relation, class,
  language and ids unchanged. 13 of them change Marathi/Gujarati text and are **unverified by a native speaker**.
- The 30 Team B "test" rows were exposed (labels listed in `VERIFICATION_PROMPT.md`), so they are `split: dev`, `origin_split: team_b_test_EXPOSED`.

## banks/distractors_v2_1.json
hi = frozen v1 Hindi bank minus 2 turns that collide with v2 QA values; mr, gu = new hand-authored neutral turns (30 user turns each),
**unreviewed**. Assistant turns = the Hindi bank's English acknowledgements.

## heldout_sealed/  (Hindi only, 24 specs, split string "test" for tooling) -- STATUS: NOT A BLIND TEST SET
**Correction (this file previously said no exposed text or label was used as a template; that was wrong).**
- Author: Claude, in the same working session in which the exposed Team B test labels had been read. Labels are by construction, not native-validated.
- `HELDOUT_INTEGRITY_AUDIT.json` (`python -m tier2.heldout_integrity_v2_1`) finds 8 of 24 specs whose frame matches an exposed test item at
  similarity >= 0.40. By inspection 6 are certain derivatives of exposed items (`0005`-`0008`, `0013`, `0020`; `0007` reuses the names of exposed
  `0105`). Another 6 are frame-identical to *dev* v1 items (new city/weekday values only), so they test generalisation over values, not new frames.
- Independence from the exposed labels therefore cannot be demonstrated and is contradicted for those items. Do not call this set blind,
  untouched or independent. Correct status: **unblinded reserve set** (useful as extra Hindi dev/robustness data; not a confirmatory test).
- Still in force: do not open the evaluator-side files (`pair_specs_heldout_v1.json`, `splits_heldout_v1.jsonl`, `build/` gold/QA reference) while
  tuning, so that the set keeps whatever reserve value it has.
- Safest next step: Team B (or a native annotator who has not seen `VERIFICATION_PROMPT.md`) authors fresh items for hi/mr/gu from the written class
  definitions only, hashes the key before delivery, and the key stays outside this repository's dev tree until the freeze.
No Marathi/Gujarati reserve or test set exists.

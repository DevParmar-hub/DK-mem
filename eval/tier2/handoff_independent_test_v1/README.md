# Independent test-set handoff package (v1) — DOCUMENTATION ONLY

**Status: prepared, not executed.** This package contains no test items, no labels and no key. No independent author, custodian, native
reviewer or written protocol approval exists yet. Nothing here may be cited as a blind, independent or validated test set.

## Files
| file | audience |
|---|---|
| `AUTHOR_INSTRUCTIONS.md` | the independent author (self-contained; with `schemas/` and `templates/AUTHOR_ATTESTATION.md`) |
| `schemas/items.schema.json`, `key.schema.json`, `review_record.schema.json` | author, custodian, reviewer |
| `templates/AUTHOR_ATTESTATION.md`, `templates/NATIVE_REVIEW_FORM.md` | author / native reviewer |
| `CUSTODY_AND_HANDOFF_PROTOCOL.md` | custodian, research lead (roles, hash commitment, guarantees and limits) |
| `REQUIREMENTS_AND_ACCEPTANCE.md` | research lead, custodian (counts, checks, ledger of done vs outstanding) |
| `../handoff_check_v1.py` (`python -m tier2.handoff_check_v1`) | custodian only (reads the key) |
| `../../tests/test_handoff_check.py` | tests of the checker, synthetic placeholder fixtures only |

## Do not send the author
The repository, `data/`, `eval/results`, any v1/v2/reserve item, `VERIFICATION_PROMPT.md`, or this README's references to counts of
existing items. Send only `AUTHOR_INSTRUCTIONS.md`, `schemas/`, `templates/AUTHOR_ATTESTATION.md`.

## Existing 24 Hindi examples
`data/tier2_v2_1/heldout_sealed/` stays **unblinded reserve data** (see `REQUIREMENTS_AND_ACCEPTANCE.md` §7 and
`data/tier2_v2_1/README_v2_1.md`). They do not count toward this package's targets.

## Requires outside action (cannot be done by tooling)
0. Convention conflicts are a required deliverable (author `conflict` fields + reviewer resolution), documented and checked by tooling.
1. Written protocol approval: class mix, roles and custodian, the author-writes-26 buffer rule, and designation of the new set as the
   held-out set with the exposed Team B set moving to dev (plan §1).
2. Independent native authors for hi, mr, gu who have not seen benchmark material.
3. Independent native review and an exclusion report.
4. Separately: written acceptance of the one-seed design, and Config C Marathi/Gujarati judge validation with native-authored cases.

# Requirements and acceptance criteria (independent test set v1)

## 1. Sample-size requirement (from `eval/evaluation_plan_v2.md` §1, §2; not lowered)
- A confirmatory claim for a language needs **n >= 20 per relation (gold-different and gold-same) in the set being reported**; the plan states
  Hindi test cells could not reach it on the old 30-item test, and that anything below 20 is reported **indicative**.
- This package therefore requires, **after native review and exclusions**, for each of `hi`, `mr`, `gu`:
  **>= 20 gold-different and >= 20 gold-same** (>= 120 pairs in total).
- Authors write **>= 26 per language x relation** (>= 156) to leave room for review exclusions. If a cell still ends below 20, the language
  x relation result is labelled indicative; the target is not reduced and no padding from dev/reserve data is allowed.

## 2. Class mix (PROPOSAL; needs written protocol approval, the plan fixes no class floors)
Per language, within the relation floors above:
| relation | kinship | honorific_register | contextual_qualifier | name_variant |
|---|---|---|---|---|
| gold-different (>= 20) | >= 8 | >= 6 | >= 4 | n/a (not allowed) |
| gold-same (>= 20) | >= 6 | >= 6 | n/a (not allowed) | >= 4 |
`contextual_qualifier` is gold-different only, so it supports FCR only; `name_variant` is gold-same only, so it supports MCR only.
Class-level results are indicative unless a class cell itself reaches 20.

## 3. Automatic acceptance checks (all must pass for every included item)
Run by the custodian with `python -m tier2.handoff_check_v1`:
1. items file has exactly `item_id, language, text_a, text_b`; ids unique and opaque; language in {hi, mr, gu}; texts non-empty, differ.
2. key has one record per item and no extras; relation in {same, different}; class in the four allowed classes; class/relation allowed
   combination (`contextual_qualifier` -> different only, `name_variant` -> same only).
3. markers occur in their messages (after the v2 Indic-safe normaliser `tier2.qa_norm`).
4. QA contract (same as `generate_tier2_v2`): roles `[a, b]` for different and `[ab]` for same; every slot has an alias in its supporting
   message(s); per-member answers are absent from the other message; forbidden aliases occur in the other message; no slot/forbidden
   overlap; the question does not contain an answer.
5. No exact or normalised duplicate text across items, and none against the reference specs.
6. Near-duplicate frame screen against reference specs (frame similarity >= 0.40): reported as **warnings for human decision**, never
   silently accepted or dropped.
7. Hashes of items and key equal the registered values; per language x relation counts reported against the target.
8. Items file contains no label-bearing field; ids carry no class, language or relation pattern.

## 3a. Convention-conflict deliverable (REQUIRED)
- The author supplies a header `conflict_report` and a `conflict` object on every record; a missing or empty report/object is a defect
  (`CONFLICT_*` / `RECORD_KEYS` codes) and the key is not accepted. An item with `author_confidence = ambiguous` must be flagged.
- The native reviewer returns a `conflict_resolution` for every item; every flagged item must be `label_stands` (with a reason) or
  `excluded` (with a reason). A flagged item with no decision blocks acceptance (`python -m tier2.handoff_check_v1 --reviews ...`).
- Conflicts are never resolved by relabelling after review: a changed label is a new item and a new revision. The final report lists
  every flagged item, its resolution and reason, and the counts of convention 1-4 objections per language. A convention that reviewers
  reject for a language is a protocol amendment needing written approval, not an item-level fix.

## 4. Human quality checks (not automatable)
- Native review of **every** item by a reviewer who is not the author (`templates/NATIVE_REVIEW_FORM.md`): label correctness, naturalness,
  class correctness, ambiguity, offensive or personally identifying content. One reviewer per language minimum; a second reviewer on a
  20% random sample with agreement reported (Cohen's kappa on relation) if two reviewers exist.
- Reviewer also resolves or excludes every author-flagged conflict (Section 3a) and states whether conventions 1-4 are acceptable.
- Items that the reviewer marks wrong, ambiguous or unnatural are **excluded and listed with the reason**; they are not edited by the
  reviewer. The author may supply a new revision; replacements are new items with new ids.

## 5. Provenance fields (key header and per item; see `schemas/key.schema.json`)
Header: `schema_version`, `revision`, `author_id` (pseudonymous), `language`, `native_language_region`, `authored_utc`, `tools_used`,
`nonce`, `conflict_report`, `attests_no_benchmark_exposure`, `attests_no_llm_drafting`. Per item: `source_kind` (`original` or
`adapted_real_chat`), `author_confidence`, `ambiguity_note`, `plausible_alternative_label`, `conflict` (required).

## 6. Status ledger (what is done vs outstanding)
| item | status |
|---|---|
| Instructions, schemas, templates, custody protocol, automatic checker | **done (documentation/tooling only; not validated by an independent author)** |
| Checker unit tests with synthetic non-benchmark fixtures | done (`eval/tests/test_handoff_check.py`) |
| Independent author(s) recruited and attested (hi, mr, gu) | **outstanding; requires people** |
| Items and key authored, hashes registered | **outstanding** |
| Native review, conflict resolutions and exclusion report | **outstanding; requires native speakers** |
| Convention-conflict deliverable defined (required fields, checks, reviewer resolution) | done (documentation/tooling) |
| Written protocol approval: class mix (§2), roles/custodian, authors-write-26 rule, replacement of the exposed set by this set | **outstanding; requires the research lead** |
| One-seed acceptance (plan §2) | **still open** |
| Config C Marathi/Gujarati judge validation with native-authored cases | **outstanding, separate from this package** |
| Held-out evaluation | **not performed; no item of this set exists** |

## 7. Status of the existing 24 Hindi examples (unchanged)
`data/tier2_v2_1/heldout_sealed/` is an **unblinded reserve set**: authored by the assistant after it read the exposed labels, 8 of 24
specs with a frame similarity >= 0.40 to an exposed item (`HELDOUT_INTEGRITY_AUDIT.json`). It is **not** blind, independent or
confirmatory, must not be counted toward the targets in §1, and must not be described as a test set.

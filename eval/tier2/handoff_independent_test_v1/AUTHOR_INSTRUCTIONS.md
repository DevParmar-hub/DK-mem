# Instructions for the independent test-set author (hi / mr / gu)

**Hand this document, the three schema files and the two templates to the author. Nothing else.** The author must not receive the DK-Mem
repository, any benchmark sentence, any label, any result, or any description of how the system under test behaves.

## 0. What you are doing
You write fresh pairs of short chat messages, in Hindi, Marathi or Gujarati, and label for each pair whether the two messages refer to
the **same person** or to **two different people**. The pairs become a held-out test set for a memory system that must decide, from two
mentions, whether to merge them. The system will never see your labels; you must not see any existing benchmark item.

You work alone, from the definitions below and your own knowledge of the language. Do not ask a language model to draft items: the
models in this research project have been exposed to the existing labels, so their drafts are not independent. If you used any tool at
all, declare it (Section 8).

## 1. Hard prohibitions (independence)
1. Do not look at, ask about, or accept hints from any existing item of this benchmark (v1, v2, "reserve", "dev", "test"), any
   verification prompt, any result table or any sentence the research team calls an "example".
2. Do not model your items on sentences you may have seen from this project. If one of your items resembles something you remember from
   the project, drop it and write a different one.
3. Do not use an LLM, translator or template generator to produce items or labels.
4. Do not share items or labels with the system builders ("tuners") at any time before the freeze announced by the custodian.
5. Do not edit the key after you have registered its hash (Section 7) without following the revision procedure there.

## 2. The unit: a pair
A pair is two **user messages**, `text_a` and `text_b`, written as one person might type to an assistant in two different chat sessions
(possibly weeks apart). Each message is a single sentence or short clause, 3-15 words, natural register, Roman or native script or the
mixture typical of chat. Both messages must mention a person.

Label each pair with exactly one relation:
- **same**: both messages refer to the same individual.
- **different**: the messages refer to two distinct individuals.

The label must be determinable from the two messages alone (plus the conventions in Section 3). If you need outside knowledge, or two
competent native speakers could reasonably disagree, the pair is ambiguous: record it (Section 6), do not guess.

## 3. Classes and conventions in force
Every pair belongs to one class. Classes are defined by what carries the identity decision:

| class | what distinguishes or links the mentions | allowed relations |
|---|---|---|
| `kinship` | kinship terms that differ by side of the family, gender, or generation, or a kinship term versus a descriptive phrase or name for the same relative | same or different |
| `honorific_register` | the politeness level of second-person address (informal / familiar / respectful), including across languages' own pronoun systems | same or different |
| `name_variant` | the same name written differently (script or spelling), with nothing else distinguishing the people | **same** only |
| `contextual_qualifier` | an identical name or term made specific by a qualifier (workplace, place, role) | **different** only |

Conventions of the benchmark (set by the research team, **not yet reviewed by native speakers**; follow them, and report any you think are
linguistically wrong in Section 6 rather than silently deviating):
1. **Same name, no distinguishing qualifier = same person.** Two messages carrying non-conflicting facts about a person with the same name
   are labelled same by convention, not as a claim about the world.
2. **Register shift with an identical vocative = same person.** Politeness changes alone do not create a new person. Two addressees
   addressed differently (different vocatives or different roles) are two people.
3. **Gold-same kinship pairs must force identity explicitly**: a shared proper name or an apposition in the text. Do not rely on
   "the speaker has only one such relative".
4. **A contextual qualifier overrides name identity**: the same name with different qualifiers is two people.

## 4. Each message must carry one checkable fact (needed for scoring)
The evaluation asks a follow-up question per pair, answered from memory. So that scoring is possible:
- **different** pairs: each message states one fact (a place, a weekday, a month, a thing) about *its* person, and the two facts must
  differ. The question about person A has A's fact as the answer and B's fact as a forbidden answer, and vice versa.
- **same** pairs: each message states a *different* fact about the one person. One combined question needs both facts.
- A fact value must not be a word that appears in both messages, and the question must not contain its own answer.
- Prefer ordinary, neutral values (cities, weekdays, months, everyday objects).

Record the facts and questions in the key (Section 5), not in the items file.

## 5. Files you deliver (schemas in `schemas/`)
- `items.jsonl`: one row per pair with only `item_id`, `language`, `text_a`, `text_b`. This is the file that can later be shown to the
  system; it must contain **nothing that reveals the label or class**.
- `key.json`: header (including a secret random `nonce` and the required `conflict_report`), then one record per `item_id` with
  `relation`, `distinction_class`, markers, facts, QA questions and accepted/forbidden answer aliases, confidence, ambiguity note,
  the required `conflict` object, provenance. Everything answer-bearing lives here.
- `AUTHOR_ATTESTATION.md` (template provided) and, later, the review record from the native reviewer.

`item_id` must be opaque (e.g. `ind_` + random hex), not sequential by class, language or relation, and unrelated to any existing id.

## 6. Recording ambiguity (do not hide it)
For every pair set `author_confidence`:
- `certain`: you would defend the label to any native speaker;
- `probable`: you are fairly sure, but you can name a rival reading;
- `ambiguous`: two readings are both defensible.

Always fill `ambiguity_note` for `probable` and `ambiguous` (what the rival reading is) and `plausible_alternative_label` when one exists.
Ambiguous pairs are **not** silently kept or dropped: the native reviewer resolves or excludes each flagged item (Section 6a);
excluded pairs are listed in the final report.

### 6a. Convention-conflict report (REQUIRED deliverable)
Every record in `key.json` carries a `conflict` object, and the key header carries a `conflict_report`. Neither may be omitted.
Flag (`conflict.flagged = true`, with `kinds` and a `description`) whenever, for that pair:
- the relation label is not clearly determined by the two messages (`relation_label_unclear`);
- a kinship term does not map to one relative, or maps differently by region/community (`kinship_term_unclear`);
- a pronoun's register or number reading is unclear, e.g. a polite form that may be plural (`pronoun_or_register_unclear`);
- the wording, spelling or script choice changes the reading (`wording_or_script_unclear`);
- the pair does not map cleanly to its class definition in Section 3 (`does_not_map_to_class_definition`);
- you believe convention 1, 2, 3 or 4 gives a linguistically wrong label here (`convention_N_wrong`).

Rules: never force an ambiguous pair into a label to avoid a flag; an item with `author_confidence = ambiguous` **must** be flagged;
write in `description` the reading you chose and the rival reading. `conflict_report` is your overall statement: how many items you
flagged, which recurring problems you saw, or, if none, what you checked. A flag is not a failure; unflagged problems that a reviewer
later finds are.

## 7. Hash registration (before anything is delivered)
1. Finish `key.json` including the 64-hex `nonce` (generate with a secure random source; never reuse; keep it secret).
2. Compute SHA-256 of the exact bytes of `key.json` and of `items.jsonl` (`certutil -hashfile key.json SHA256` on Windows,
   `sha256sum key.json` elsewhere).
3. Send the two hashes, your pseudonymous `author_id` and a timestamp to the custodian (the person who gave you this document; a
   person who does not build or tune the system). Send nothing else at this step. Only after the custodian acknowledges receipt do you
   deliver `items.jsonl` and `key.json`, to the custodian only.
4. Keep `key.json` private until the custodian's reveal instruction. If a defect must be fixed, increment `revision`, recompute and
   re-register both hashes; the old hashes and the reason for the change are kept in the log.

## 8. Quantities, quality and self-checks
Write **at least 26 pairs for every cell of language x relation** (gold-different and gold-same, per language you cover); after review at
least 20 per cell must remain. Recommended class mix per language and relation (a proposal, still pending written approval; extra pairs
may go to any allowed class):

| relation | kinship | honorific_register | contextual_qualifier | name_variant |
|---|---|---|---|---|
| different (>= 26 written) | >= 10 | >= 8 | >= 5 | not allowed |
| same (>= 26 written) | >= 8 | >= 8 | not allowed | >= 5 |

Before delivery check:
- no text is duplicated across pairs; no two pairs differ only by a swapped city/weekday value;
- every pair has the right number of QA roles and the answer appears in the supporting message(s) but not in the other one;
- the class matches the table in Section 3 and the label is allowed for it;
- 15+ distinct names, 15+ distinct values per language: do not reuse one frame with changed values;
- the language is the one declared; code-mixing is natural and not decorative.

## 9. Provenance you must state
Native language and region/dialect, years of use, authored date, whether items are original or adapted from real chat (anonymised,
consent noted), any tool used (including spell checkers and translators), and the attestation in the template.

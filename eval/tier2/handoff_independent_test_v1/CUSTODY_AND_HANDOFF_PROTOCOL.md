# Custody and leakage-safe handoff protocol

## 1. Roles (names to be assigned in the written approval; one person may not hold two marked roles)
| role | who | may see items | may see key |
|---|---|---|---|
| **Author** | independent native speaker(s), one per language, who have not seen any benchmark item or label | their own | their own |
| **Custodian** | a person who does **not** tune DK-Mem (e.g. Team B lead or the research supervisor) | yes | yes, held sealed |
| **Native reviewer** | a native speaker different from the author, not a tuner | yes | yes, at review time only |
| **Tuner** | anyone who changes a prompt, judge, lexicon rule, threshold or code of DK-Mem (Team A, Member 3, and the assistant model used in this repository) | **no, until the freeze** | **never before the freeze** |

The assistant model that built the v2.1 repair package is a tuner for this purpose: it has read the exposed labels and must not receive the
items or the key.

## 2. Sequence
1. Custodian sends the author `AUTHOR_INSTRUCTIONS.md`, `schemas/`, and the two templates, nothing else.
2. Author writes `items.jsonl` + `key.json`, computes both SHA-256 hashes (the key contains a secret nonce so a low-entropy label file
   cannot be brute-forced from its hash) and sends **only the hashes** to the custodian. The custodian records them, with a timestamp, in
   a log the tuners can read but not write (`hash_log.md`, append-only, signed or held by the supervisor).
3. Custodian acknowledges; author delivers `items.jsonl` and `key.json` **to the custodian only**.
4. Custodian runs the automatic checks (`python -m tier2.handoff_check_v1`, see below) and returns to the author only generic defect
   codes (`QA_ROLES`, `ANSWER_IN_OTHER_TEXT`, ...), never labels. Fixes are new revisions with new registered hashes.
5. Native review (`templates/NATIVE_REVIEW_FORM.md`): the reviewer sees items and key and returns, for every item, a verdict and, for
   every author-flagged convention conflict, a resolution (`label_stands` or `excluded`) with a reason. Defects are resolved by the
   author with a new revision; items the reviewer rejects are excluded and listed. A flagged item without a recorded decision blocks
   acceptance; a convention rejected for a language is escalated as a protocol amendment.
6. Tuners work on the **dev** data only. Prompts, lexicon rules, judge, tau and code are frozen in the freeze file.
7. After the freeze file exists, the custodian reveals `key.json` and `items.jsonl`; anyone can verify both against the logged hashes;
   only then are conversations generated and scored once.

## 3. What the custodian must run (evaluator side; never before step 3, never by a tuner)
```
python -m tier2.handoff_check_v1 --items items.jsonl --key key.json \
    --expect-items-sha256 <logged> --expect-key-sha256 <logged> \
    --reference-specs <dev specs, reserve specs, exposed Team B specs> --target 20
```
The reference specs are used only to detect duplicated texts and near-duplicate frames; the tool prints item ids and defect codes, never
labels or QA values.

## 4. What this process can guarantee
- **Tamper evidence:** the key and the items in the custodian's possession are the ones that were committed to before delivery.
- **Procedural separation:** if the roles are respected, no tuner has seen items or labels at the time prompts/lexicon/tau are frozen.
- **Auditability:** attestation, revisions, review verdicts, exclusions and hashes are on record.

## 5. What it cannot guarantee
- **Independence by attestation only.** Nothing proves the author did not see benchmark material or used a model; it is a signed
  declaration plus an automatic similarity screen against known items, which catches copying, not shared ideas.
- **Hashes prove immutability, not correctness** or that the key was never read by a tuner; custody is a human control.
- **Distribution overlap is unavoidable.** The same finite set of kinship terms, pronouns and name variants will appear; resemblance to
  dev items in *kind* is expected and is not leakage by itself.
- **Prior exposure remains.** Several lexical conventions and the plan itself are shaped by v1/v2 results; the final evaluation is not
  blind to those (plan §7). A new test set removes label exposure of *items*, not research-process exposure.
- **No native validation of conventions** until the reviewers have checked them; a convention that is wrong makes labels
  wrong in a consistent way that agreement statistics will not reveal.
- **One author per language is a single point of failure** for idiolect; the review and a second-author sample reduce but do not remove it.
- If any tuner sees the key or the items before the freeze, the set is **dev data**, not a test set, and the claim must be withdrawn.

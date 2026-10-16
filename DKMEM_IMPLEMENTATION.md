# DK-Mem: Canonical Implementation Reference

This document describes exactly what is implemented in this repository today, file by file and function by function. It is grounded entirely in the code under `dkmem/` and the real experiment outputs under `tier1_results/` — not in the research plan. Anywhere the research plan describes something that does **not** exist in code yet, this document says so explicitly under "Not implemented".

> **Revision (scope alignment, 2026-10-07).** The research direction changed to `DKMEM_NEW_RESEARCH_IDEA.md` (stage attribution over configurations A–D). The existing code was aligned to it *without* building the A–D system: distinction scope narrowed to kinship / register / name_variant (`dkmem/memory/scope.py`); a final extraction prompt `mem0_extraction_v4` added (v1–v3 kept) and made the default; `apply_gate()` added so the gate can veto a host system's proposed merge; similarity made pluggable and separated from the gate (`dkmem/memory/consolidation.py` now holds the glue); A–D / DK-Mem ON-OFF vocabulary added (`dkmem/config.py`); the Tier 1 contracts (JSON schemas, class mapping, manifest) updated. The six runs in `tier1_results/` predate this change and were produced under the old scope (see §14).
>
> **Revision (A–D harness, 2026-10-07; Config B frozen 2026-10-08).** The stage-attribution pipeline for Configs A–D (`dkmem/pipeline/`, §13b) has the LLM merge judge (`dkmem/memory/judge.py`), the native-language extractor of Config B (`dkmem/memory/native_extract.py`, frozen prompt `native_b_v1`) and the bge-m3 embedding metric (`dkmem/backends/embedding.py`). Tested with scripted fake models, a 20-record A–C smoke test, and a 173-record × 1.5B/3B/7B check of the Config B prompt; **no full A–D experiment has been run on a real model yet**, and the baselines are not built. The first real run is specified in `DKMEM_FIRST_RUN.md`.

>
> **Revision (baselines and offline evaluation, 2026-10-08).** `dkmem/baselines/` (a hash-pinned Mem0 OSS v1.0.11 reproduction and the never-merge / flat-RAG baseline), the prompt-informed merge judge `merge_judge_informed_v1` (`dkmem/memory/judge.py`) and `dkmem/eval/` (FCR/MCR per the Tier 1 contract, the exact raise-τ sweep, the DK-Mem ablation report, a fairness check) were added; see §13c and `DKMEM_BASELINES.md`. The frozen A–D behaviour is unchanged (an optional `judge_prompt` argument defaults to `merge_judge_v1` and leaves its fingerprint unchanged). Tested with fake models only: **no baseline has been run on a real model.** The memory store (`dkmem/store/`) predates this revision and is not described in this document yet.
>
> **Revision (Tier 2 Config C/D preparation, 2026-10-14).** Tier 2 (controlled multi-session injection benchmark) now has a runner, contract validation and a second, counter-confound benchmark arm under `eval/tier2/` (§13d). Config C on Tier 2 uses a new, separately versioned identity judge (`merge_judge_entity_t2_v2`) on **Qwen2.5-7B**, a different judge backbone from Tier 1, after Qwen2.5-3B failed two pre-registered validations. After Config D and combined C+D smoke tests, the **full Tier 2 experiment ran on 2026-10-14** on both arms (69 conversations each; C and D, gate off/lexicon; seed 0), scored with an analysis plan frozen before any full-run output existed. Results are descriptive and rest on provisional labels (§13d). Tier 1 code, frozen prompts (`merge_judge_v1` sha256 `3855ef65…` unchanged), the v1.0 benchmark and all earlier outputs are unchanged. A full Tier 1 A–D run (Qwen2.5-3B, seed 0) exists separately in `results/full_ad_3b_s0_20261010/` (key-free decision counts; see its `RESULTS_REPORT.md`); it is not summarised here.

---

## 1. One-paragraph overview

DK-Mem tests one idea: when a multilingual utterance is normalized into an English "gloss" for memory storage, a source-language distinction (e.g. Hindi *chachi* vs *mausi*, both "aunt" in English) can get lost, causing two genuinely different facts/entities to look identical and get wrongly merged. The fix implemented here is to extract a second field, `distinction`, alongside the English gloss, and gate every merge decision on both the gloss similarity **and** whether the two entries' `distinction` fields actually agree.

## 2. End-to-end pipeline diagram

```
                      ┌─────────────────────┐
  one utterance  ───► │   EXTRACTION STAGE   │
  (side "a" or "b")   │  (lexicon and/or     │
                      │   Qwen2.5-3B-Instruct)│
                      └──────────┬───────────┘
                                 │
                                 ▼
                      Extraction{ gloss, distinction,
                                  surface, lang_profile,
                                  backbone, prompt_id, seed }
                                 │
                   (one Extraction per side, "a" and "b")
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │  SIMILARITY STAGE    │
                      │  gloss_similarity()  │   sim = difflib ratio
                      │  (similarity.py)     │   on normalized glosses
                      └──────────┬───────────┘
                                 │  sim (float, 0..1)
                                 ▼
                      ┌─────────────────────┐
                      │   GATE STAGE         │
                      │   gate() (gate.py)   │
                      │  compares distinction│
                      │  dicts, feature by   │
                      │  feature             │
                      └──────────┬───────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
        incompatible      underdetermined        compatible
              │                  │               (sim decides)
              ▼                  ▼              ┌────┴────┐
         keep_both        link_unresolved        ▼         ▼
                                              merge     keep_both
                                 │
                                 ▼
                      MergeEvent / PairwiseEvalRecord
                      (written to disk as JSON)
```

There is **no live, queryable "memory store"** anywhere in this pipeline (see §13). Every run — whether a unit test, a `MergeEvent` comparison, or a full Tier 1 episode — is a single, self-contained extraction-then-gate computation on exactly the entries just produced. Nothing is retrieved from a prior episode.

---

## 3. Core data contracts — `dkmem/memory/schema.py`

Three frozen `dataclasses`, each with strict `__post_init__` validation (wrong type or shape raises `SchemaError` immediately — nothing is silently coerced except numeric widening to `float`).

### `ProbeItem`
A hand-authored (or synthetic-fixture) minimal-pair test case: two utterances (`utt_a`, `utt_b`), a language tag, the gold label `gold_same_entity`, and which `distinction_class` is supposed to separate them. Used only in the research fixtures/tests, **not** in the real Tier 1 run (Tier 1 uses `Tier1Record` instead, see §12).

### `Extraction` — the actual stored memory entry
```python
Extraction(
    pair_id: str, side: "a"|"b",
    raw_output: str,            # Qwen's verbatim text, or "" if no LLM ran
    gloss: str,                 # normalized English retrieval key
    distinction: dict[str,str], # e.g. {"kinship": "chachi"}
    surface: str,                # verbatim original utterance
    lang_profile: dict[str,float], # e.g. {"hi": 0.8, "en": 0.2, "script_mix": 0.1}
    backbone: str, prompt_id: str, seed: int,
)
```
This is the single object every later stage (similarity, gate, Tier 1 I/O) consumes. It is immutable (`frozen=True`); `dkmem_extract.py` builds a *new* `Extraction` via `dataclasses.replace` rather than mutating one.

### `MergeEvent` — one consolidation decision
```python
MergeEvent(pair_id, policy, tau, sim, decision, reason, backbone, seed, prompt_id)
```
`decision` must be one of `("merge", "supersede", "keep_both", "link_unresolved")` — this is the single source of truth for the internal decision vocabulary (`DECISIONS`). **`supersede` is defined here but never produced by any code in this repo.**

### JSONL helpers
`write_jsonl` / `read_jsonl` serialize any of the above, one JSON object per line, UTF-8, LF-terminated. `write_jsonl(..., append=True)` safely resumes a log without corrupting a truncated last line.

---

## 4. Frozen prompts — `dkmem/memory/prompts.py`

Four versioned prompt templates (`mem0_extraction_v1`, `_v2`, `_v3`, `_v4`), each a `PromptTemplate(prompt_id, system, user_template, output_keys, examples)`. A prompt's text must never change once an experiment has logged its `prompt_id` — `PromptTemplate.sha256` fingerprints the exact text so a change would be detected by the cache (§10). `DEFAULT_EXTRACTION_PROMPT` (currently **v4**) is what `extract`, `cached_extract` and `dkmem_extract` use when no prompt is passed.

All three instruct Qwen to return **exactly**:
```json
{"gloss": "...", "distinction": {...}, "surface": "..."}
```
- `gloss`: one third-person English sentence, generic nouns only (kinship collapses to "uncle"/"aunt" etc.), no non-English words, no trailing period.
- `distinction`: an object using only the fixed keys the prompt allows, populated only when the utterance actually marks that feature. v1–v3 allow 7 keys (`kinship`, `register`, `politeness`, `evidentiality`, `classifier`, `temporal_deixis`, `name_variant`); **v4 allows only the 3 in-scope keys** (`kinship`, `register`, `name_variant`).
- `surface`: the utterance copied back verbatim (used as an integrity check, see §6).

v1 → v3 differ in how much the system prompt explains and exemplifies each distinction key (v2 has 13 inline examples; v3 has the same 13 as separate user/assistant chat turns plus extra negative rules). In an earlier 20-item dev-set check on Qwen2.5-3B (greedy), target-feature distinction accuracy was v1 7/20, v2 10/20, v3 10/20 (exact-match 7/9/6 of 20; those items were also used to diagnose failures, so the numbers are optimistic).

**v4 (final, current default)** is v3 restricted to the in-scope classes: the politeness, evidentiality, classifier and temporal_deixis definitions are removed, together with the examples that only demonstrated them (the two Turkish examples stay and tag only the name). One sentence is added ("Use only the keys below", as in v1) because the parser rejects any other key. v3 was chosen as the base because on the 12 in-scope probe sides of that check v2 and v3 were tied (7/12), v3's extra spurious keys were mostly the now-removed `politeness`, and v3 had no "you"/"My …" gloss violations (v2: 4). **v4 has not been run on a model yet**; because its text differs from v3, the 10/20 figure does not carry over. v1–v3 are unchanged and kept for comparison; their fingerprints are frozen in `tests/test_prompts.py`.

`PromptTemplate.render(utterance)` returns chat messages (`[{"role": "system", ...}, {"role": "user", ...}]`) — no generation or parsing happens in this file.

---

## 5. Qwen backend — `dkmem/backends/llm.py`

`HFGenerator` wraps a Hugging Face causal LM. No prompt design or output parsing lives here — purely "take prompts in, get raw text out."

- **`ModelConfig`**: `model_id` (default `"Qwen/Qwen2.5-3B-Instruct"`), `revision`, `device` (default `"cuda:0"`), `dtype` (default `"float16"`, fp16 because the target hardware is a Kaggle T4 with no native bf16), `use_chat_template`.
- **`GenerationParams`**: `max_new_tokens=256`, `do_sample=False` (greedy by default), `temperature`/`top_p`/`top_k`/`repetition_penalty`, `seed=0`, `batch_size=8`.
- **`HFGenerator.load(config)`**: loads tokenizer + model, forces left-padding (required for decoder-only batched generation), and **overwrites the checkpoint's shipped generation defaults** (Qwen2.5-Instruct ships `temperature=0.7, top_p=0.8, top_k=20, repetition_penalty=1.05`) with neutral ones — so only `GenerationParams` controls decoding, never the checkpoint's own defaults.
- **`HFGenerator.generate(prompts, params)`**: batches prompts (`batched()`), calls `set_seed(params.seed)` once per call, runs `model.generate`, strips the prompt and special tokens off the output, returns one raw string per prompt in input order. No JSON parsing happens here — that's `extract.py`'s job.
- **`run_info()`**: provenance dict (backbone, model config, torch/transformers versions, chat-template hash) — used for cache keys and audit, not for decisions.

---

## 6. Baseline ("Mem0-style") extraction — `dkmem/memory/extract.py`

This is the unmodified, frozen extractor that both DK-Mem variants build on.

**`extract_many(items, generator, params, prompt)`**: for a batch of `(ProbeItem, side)` pairs, renders each into a prompt, calls `generator.generate(...)` once for the whole batch, then validates and parses every raw output via `parse_model_output`.

**`parse_model_output(raw_output, utterance, prompt)`** — strict validation, nothing is auto-repaired:
1. Must be exactly one JSON object (`json.loads` with `object_pairs_hook` that rejects duplicate keys) — code fences, extra text, or multiple objects all raise `ExtractionError`.
2. Must have exactly the prompt's `output_keys` — no missing, no extra.
3. `gloss` must be a non-empty string.
4. `distinction` must be a dict using only the keys registered for the prompt in use (`DISTINCTION_KEYS[prompt_id]`: the 7 legacy classes for v1–v3, the 3 in-scope classes for v4 — a stray key such as `politeness` under v4 raises `ExtractionError`); for the 3 closed-vocabulary legacy keys (`politeness`, `evidentiality`, `temporal_deixis`), the value must be one of a fixed small set (`CLOSED_DISTINCTION_VALUES`).
5. `surface` **must equal the input utterance exactly, character for character.** This is the integrity check that catches a model paraphrasing or truncating the original text instead of copying it.

Any failure raises `ExtractionError` carrying the raw output (nothing generated is ever silently dropped); a batch failure raises `ExtractionBatchError` holding every per-item failure plus the successful extractions.

**`derive_lang_profile(lang, utterance)`** — a fully deterministic function, **never produced by the model**:
- Single-language tag (e.g. `"hi"`) → `{"hi": 1.0, "en": 0.0}`.
- Code-mixed tag (e.g. `"hi-en"`) → the share of Latin-script tokens that are in a small hardcoded English word list (`_ENGLISH_WORDS`), the rest attributed to the other language.
- `script_mix`: share of tokens not in the utterance's majority script.

**`build_extraction(...)`** assembles the final `Extraction`, combining the parsed `(gloss, distinction, surface)` with the deterministic `lang_profile` and the caller-supplied `backbone`/`seed`/`prompt_id`.

---

## 7. The distinction lexicon — `dkmem/memory/lexicon.py` + `distinction_features.json`

A static, hand-curated JSON table (schema version `"1.0"`) mapping source-language surface markers to `Extraction.distinction` values. **Currently 15 entries total**, all pilot-reviewed, all Hindi:

| Language | Distinction class | Count | Values |
|---|---|---|---|
| `hi` (Hindi) | `kinship` | 12 | tau, chacha, tai, chachi, mama, mausa, mami, mausi, nana, dadi, nani, bua |
| `hi` (Hindi) | `register` | 3 | tu, tum, aap |

The Turkish `-mış/-miş/-muş/-müş` evidentiality entry was **removed** with the scope change. `evidentiality`, `politeness`, `classifier` and `temporal_deixis` are out of scope (`dkmem/memory/scope.py`); `name_variant` is in scope but has **no entries** (an open vocabulary; whether and how a dictionary covers it is undecided). The Kinbank-generated kinship slice, honorific/register entries beyond Hindi, and a non-Indic kinship slice are still to be built. The loader accepts any snake_case class; `tests/test_lexicon.py` checks the shipped file stays within the in-scope classes.

Each `LexiconEntry` has a `match_type` of `exact_word`, `prefix`, `suffix`, or `regex`, a tuple of `surface_forms`, and a `value`. `load_lexicon()` validates every entry and rejects: duplicate IDs, and two entries that map the *same* surface form (for the same lang/class/match_type) to *different* values. For closed-vocabulary classes, an entry's `value` must already be in `CLOSED_DISTINCTION_VALUES` — a lexicon entry can never produce a value the extraction schema would reject downstream.

---

## 8. The matcher — `dkmem/memory/matcher.py`

Pure deterministic text scanning — no model, no `Extraction` objects, no dependency on `extract.py`.

1. **Tokenize** (`_tokenize`): split on whitespace, trim only Unicode punctuation/symbol characters off each token's edges (deliberately *not* `\W`, since `\W` would also strip Devanagari vowel signs that are genuinely part of the word).
2. **Match** (`find_matches`): for one language code, scan every token against every lexicon entry for that language; `exact_word`/`prefix`/`suffix` compare case-insensitively (`casefold`), `regex` entries use `re.search` as-is.
3. **Resolve conflicts** (`match_distinctions`): if two matches disagree on the value for the *same* distinction class, break the tie deterministically: higher `priority` wins → earlier token position wins → longer matched span wins → lexicographically lower entry `id` wins. Two matches that *agree* are not a conflict.

Output: `dict[str, str]`, exactly the shape `Extraction.distinction` expects.

---

## 9. The lexicon-first, model-second cascade — `dkmem/memory/dkmem_extract.py`

This is "DK-Mem's" actual extraction strategy (as opposed to the raw baseline in §6):

1. Run the unmodified baseline extraction (`extract_many`, cached or not) to get a normal `Extraction`, including the model's own guess at `distinction`.
2. Scan the utterance with the matcher (§8), once per `-`-separated language component (so `"hi-en"` checks both `hi` and `en` entries).
3. Per distinction class:
   - Lexicon found **exactly one** candidate value → **override** the model's value (lexicon wins).
   - Lexicon found **multiple conflicting** candidate values (`_ambiguous_classes`) → **set the lexicon result aside, use the model's value for that class** (none if the model has none).
   - Lexicon found **nothing** → the class is absent. The model is **not** consulted (spec Sec 5.3: the LLM is called "only for spans the lexicon flags as ambiguous"). *Changed 2026-10-08: before, the model's value was kept for unmatched classes too; runs from that cascade are not comparable.*
4. Return a new `Extraction` (via `dataclasses.replace`) with `distinction` replaced by the merge above and `prompt_id` suffixed with `+dkmem_lexicon` (`dkmem_prompt_id()`) — so a lexicon-augmented record is never mistaken for, or cache-collides with, a pure baseline record.

`dkmem_extract_many` / `dkmem_extract` are the batch/single-item entry points; this is what `tier1/runner.py`'s `dk-mem-lexicon-llm` strategy calls.

---

## 10. Persistent extraction cache — `dkmem/memory/cache.py`

**This is the only thing in the codebase that persists an `Extraction` across calls — and it is explicitly a cache, not a memory store** (nothing ever queries it by meaning; it is keyed purely by configuration identity).

- **Format**: append-only UTF-8 JSONL, one line per entry: `{"key": <sha256 hex>, "key_fields": {...}, "extraction": {...}}`.
- **Key**: SHA-256 of the canonical JSON of: `pair_id`, `side`, `utterance`, `lang`, `prompt_id` + its text fingerprint, `backbone`, every `GenerationParams` field (seed included), and optional `backend_info`. Two different configurations (different seed, different prompt version, different model) never collide.
- **Verification on every load and every `put`**: an entry's stored `Extraction` must exactly equal what re-parsing its own `raw_output` through the current extraction code produces (`_verify`/`_expected_extraction`). A mismatch raises `CacheError` — the cache can never silently serve a stale or hand-edited result.
- **Write-once semantics**: `put()` on an existing key with a *different* result raises `CacheConflictError` and writes nothing; re-putting an identical result is a no-op.
- `cached_extract_many`/`cached_extract` wrap `extract_many`/`extract`, generating only the cache misses and persisting them before returning.

**Not used anywhere in the real Tier 1 run** (`tier1/runner.py` explicitly does not pass a `cache`) — Tier 1 episodes are deliberately independent with zero carried-over state (see §12, §13).

---

## 11. Similarity — `dkmem/memory/similarity.py` and `consolidation.py`

`similarity.py` owns only candidate pairs and text similarity and **imports nothing from the gate**. The glue that feeds a similarity score into the gate is `evaluate_pair` in `dkmem/memory/consolidation.py` (moved there from `similarity.py`).

### The formula

```python
def normalize_gloss(gloss):
    return re.sub(r"\s+", " ", gloss).strip().casefold()

def gloss_similarity(gloss_a, gloss_b):
    x, y = sorted((normalize_gloss(gloss_a), normalize_gloss(gloss_b)))
    return difflib.SequenceMatcher(None, x, y).ratio()
```

- `normalize_gloss` only casefolds and collapses whitespace — purely textual, no semantics.
- The two normalized strings are **sorted** before comparing, solely to make the result independent of call order (`SequenceMatcher.ratio()` is not perfectly symmetric on its own).
- `SequenceMatcher.ratio()` implements the **Ratcliff/Obershelp algorithm**:

  $$\text{ratio} = \frac{2M}{T}$$

  where `T = len(x) + len(y)` and `M` is the total number of matching characters found by recursively locating the single longest contiguous matching block between the two strings, then recursing on the text before and after that block, summing all matched-block lengths. It is a **character-sequence** metric — no tokenizer, no embeddings, no word-level meaning at all.

This is explicitly documented (module docstring) as a deterministic, free, reproducible **stand-in** for a real embedding similarity (e.g. bge-m3) — not the paper's intended final metric. No embedding model is called anywhere in this repository.

### Pluggable metrics: `SimilarityMetric`, `entry_similarity`
```python
SimilarityMetric(name: str, fn: Callable[[str, str], float])   # frozen dataclass
DIFFLIB_RATIO = SimilarityMetric("difflib_ratio_v1", gloss_similarity)
DEFAULT_SIMILARITY = DIFFLIB_RATIO
entry_similarity(entry_a, entry_b, metric=DEFAULT_SIMILARITY, text_field="gloss")  # "gloss" | "surface"
```
- Calling a `SimilarityMetric` checks the score is finite and within [0, 1] (the range `pairwise_eval.schema.json` requires) and **raises `SimilarityError` instead of clipping**: the reported score must stay raw, so a metric like cosine similarity (range [-1, 1]) has to map itself into [0, 1] explicitly.
- `text_field` selects which `Extraction` field is compared: the gloss by default, the verbatim surface for configurations that compare surface text (C/D in `dkmem/config.py`).
- Replacing the placeholder with a real embedding is therefore: wrap its `(text_a, text_b) -> float` in a `SimilarityMetric` and pass it as `similarity=` to `evaluate_pair` or the Tier 1 runner. Neither the gate nor any caller changes. (A real τ also has to be chosen for that metric: `DEFAULT_TAU = 0.85` belongs to the difflib ratio.) No embedding metric exists yet.

### `candidate_pairs(entries_a, entries_b)`
The cross product of two entry lists (all of `entries_a` must be `side="a"`, all of `entries_b` must be `side="b"`, all must share one `pair_id`). This is **not retrieval** — it does not search any store; it assumes the two entry lists for one episode are already known. Today, every extractor produces exactly one entry per side, so this is always a single pair.

### `consolidation.evaluate_pair(entry_a, entry_b, tau, *, policy, discriminative_features, similarity, text_field)`
Computes `sim = entry_similarity(...)` once, passes it unchanged into `gate.build_merge_event(...)` (the standalone `gate()` policy, §12), and returns the resulting `MergeEvent`. `sim` is never clipped, rounded, or overwritten after this point. The two entries must share backbone, prompt_id, seed and pair_id.

---

## 12. The compatibility gate — `dkmem/memory/gate.py`

This is the paper's actual mechanism: replacing `merge(a,b) if sim > tau` with `merge(a,b) if sim > tau AND compatible(distinction_a, distinction_b)`.

### `DEFAULT_DISCRIMINATIVE_FEATURES`
```python
{"kinship", "register"}      # = dkmem.memory.scope.DISCRIMINATIVE_CLASSES
```
These are the in-scope cannot-link classes. `name_variant` is a recognized in-scope `distinction` key but is **not** in this set, so it never participates in gating: Sec 6.1 of the research plan includes same-entity name variants (Priya / प्रिया) that should merge, so a differing name variant must not block a merge. Whether name variants should constrain merging at all is undecided. The pre-rescope six-feature set is kept as `LEGACY_DISCRIMINATIVE_CLASSES` in `dkmem/memory/scope.py` (used by the frozen fixtures and as an ablation override).

### `compatible()` / `_compatibility_detail()` — pure dict comparison, zero model/embedding calls
Loop over the discriminative features **in sorted order**; for each, look at `a = distinction_a.get(feature)`, `b = distinction_b.get(feature)`:

| Both sides | Result for this feature |
|---|---|
| Same value (or both absent) | nothing — no finding |
| Different values | candidate **incompatible** |
| One present, one absent | candidate **underdetermined** |

The function keeps the *first* incompatible finding and the *first* underdetermined finding it encounters (in sorted-feature order), then:
- Any incompatible finding exists → overall `"incompatible"` (wins even over an underdetermined finding on a different feature).
- Else any underdetermined finding exists → `"underdetermined"`.
- Else → `"compatible"`.

### `gate(distinction_a, distinction_b, sim, tau, discriminative_features)` → `(compatibility, decision, reason)`

| Compatibility | Decision | Does τ matter? |
|---|---|---|
| `incompatible` | `keep_both` | **No** — always, regardless of `sim` |
| `underdetermined` | `link_unresolved` | **No** — always, regardless of `sim` |
| `compatible` | `merge` if `sim >= tau`, else `keep_both` | **Yes** — the only branch where similarity is consulted |

**τ (tau) is a plain caller-supplied float, not a constant inside `gate.py`.** In the real Tier 1 runs it is `DEFAULT_TAU = 0.85` (`dkmem/tier1/runner.py`). It is recorded unchanged on every output record (`MergeEvent.tau` / `PairwiseEvalRecord.threshold`).

`build_merge_event(...)` wraps `gate()` into a `MergeEvent`, encoding the compatibility label as the leading word of `reason` (e.g. `"incompatible kinship values: chachi vs mausi"`).

### `apply_gate(proposed, distinction_a, distinction_b, discriminative_features)` → `GateResult` — the veto layer
`gate()` derives its own merge proposal from `sim >= tau`; it cannot sit in front of another system's decision. `apply_gate` can: the *host* mechanism (an LLM judge or an embedding threshold, as in configurations A–D) decides first, and the gate only intervenes when the host proposed a unifying decision (`merge` or `supersede`):

| Host proposed | Compatibility | Final decision |
|---|---|---|
| `merge` / `supersede` | `incompatible` | `keep_both` (vetoed) |
| `merge` / `supersede` | `underdetermined` | `link_unresolved` (vetoed) |
| `merge` / `supersede` | `compatible` | unchanged |
| `keep_both` / `link_unresolved` | any | unchanged (nothing to veto) |

`GateResult(compatibility, proposed, decision, reason)` has a `vetoed` property (`decision != proposed`); `compatibility` is reported even when nothing is vetoed. Reasons read e.g. `vetoed supersede: incompatible kinship values: chachi vs mausi`. For a host that would merge, `apply_gate("merge", …)` and `gate(…, sim >= tau)` give identical results.

**One deliberate difference from `gate()`:** `gate()` links an underdetermined pair *regardless of* `sim` (even far below τ), while `apply_gate` never links a pair the host would not have merged. This matters for the unresolved-link (bloat) count: in the six existing runs, 38 of 138 LLM rows and 10 of 173 lexicon-only rows are underdetermined, and under veto-only semantics only those at or above τ would be links (7 of the 38 LLM rows and 7 of the 10 lexicon-only rows; all 10 lexicon-only rows are the Turkish evidential pairs, §14). The Tier 1 runner still uses `gate()`; whether it should switch is an open decision.

**Neither function produces `supersede` by itself** — recognizing an "update" (e.g. a changed address) rather than a duplicate needs a rule this codebase does not implement. `apply_gate` can only veto a `supersede` that a host proposed.

---

## 13. Tier 1 evaluation pipeline — `dkmem/tier1/`

This is where the above pieces are actually run against real data, producing the files Team B scores externally.

### Input — `tier1/io.py::load_tier1_input`
Reads **only** `data/tier1/eval_input/teamA_tier1_v2.jsonl` (173 records), and refuses to proceed unless its SHA-256 matches a hardcoded expected hash (`TIER1_INPUT_SHA256`) and it has exactly 173 lines. Each line is a `Tier1Record`: `eval_pair_id`, `language`, `utterance_a`, `utterance_b`, `utterance_a_id`, `utterance_b_id`, `opaque_entity_id_a`, `opaque_entity_id_b`. The two `opaque_entity_id_*` fields are **passthrough only** — copied straight to the output's `gold_entity_id`, never read by extraction, the lexicon, or the gate.

### Two strategies — `tier1/extraction.py` + `tier1/runner.py`

| Strategy | Function | LLM call? | `backbone` recorded |
|---|---|---|---|
| `dk-mem-lexicon` | `extract_lexicon_only` | No | `null` |
| `dk-mem-lexicon-llm` | `dkmem_extract_many` (§9), default prompt v4 | Yes, Qwen2.5-3B-Instruct | model id |

`extract_lexicon_only` (no-LLM strategy): `distinction` comes purely from `match_distinctions`; since there is no translation step, `gloss` is explicitly set to the **raw surface utterance, unchanged** (not a real English gloss) — the module docstring states this is reported honestly, not disguised.

### Per-episode independence
Both `run_episode_*` functions take exactly one `Tier1Record` and return a fresh result with **no shared mutable state, cache, or carried-over object** between episodes — the only shared object is the read-only `Lexicon`. If extraction fails for either side (bad model output, unsupported language tag), that episode simply yields **no entries, not a crash** — matching the eval contract's "if an utterance yields no entries, emit nothing; Team B scores that pair as 'no entry'".

### Translating to the external contract — `tier1/io.py`
`dkmem.memory.schema.DECISIONS` → `pairwise_eval.schema.json`'s vocabulary:

| Internal (`gate.py`) | External (`pairwise_eval.jsonl`) |
|---|---|
| `merge` | `merge` |
| `keep_both` | `no_merge` |
| `link_unresolved` | `underdetermined_link` |
| *(never produced)* | `supersede` |

Internal distinction keys map onto the external schema's class enum, which now holds only the three in-scope classes: `kinship`→`kinship`, `register`→`honorific_register`, `name_variant`→`name_variant`. An out-of-scope key (e.g. from a legacy prompt) has no external name and raises `Tier1InputError`. **If an entry's internal `distinction` dict has more than one key, only the alphabetically-first one is reported externally** — a serialization limitation; the gate itself still considers every key when deciding merge/no_merge.

`write_run_manifest` / `write_pairwise_eval` produce the two files per run, validated against `run_manifest.schema.json` / `pairwise_eval.schema.json`. The manifest can now also record two optional fields: `pipeline_config` (`"A"`–`"D"`) and `dkmem_mode` (`"off"`, `"lexicon"`, `"lexicon+llm"`), defined in `dkmem/config.py`. `dkmem_mode` must agree with the strategy (`dk-mem-lexicon` → `lexicon`, `dk-mem-lexicon-llm` → `lexicon+llm`, anything else → `off`).

### Contract changes made in the scope alignment (need Team B sign-off)
- `strategy` enum (both schemas, also `dkmem.config.STRATEGIES`): `lightmem`, `trag`, `crossrag` removed; `embedding-threshold`, `raise-tau`, `prompt-informed-judge` added; `mem0` kept (config A vs B is told apart by `pipeline_config`). `run_manifest.schema.json` now actually enforces the enum (it previously only said "same enum as pairwise_eval").
- `distinction.class` enum narrowed from 7 to 3 classes.
- `run_manifest.schema.json`: optional `pipeline_config` and `dkmem_mode`.
- `compatibility: null` now documented as "DK-Mem off".
- `tier1_eval_contract.md`, `experiment_output_spec.md` and the `teamA_*` handoff files still describe the old strategy and class lists; they were not edited.

---

## 13b. Stage-attribution harness (Configs A–D) — `dkmem/pipeline/`

Implements the four configurations of `DKMEM_NEW_RESEARCH_IDEA.md` §6.2, each runnable with the DK-Mem gate off, `lexicon` or `lexicon+llm`.

| Config | Extraction → stored text | Host merge decision | Isolates |
|---|---|---|---|
| **A** | `mem0_extraction_v4` (English-forced) → `gloss` | LLM judge on the glosses | L1 |
| **B** | `native_b_v1` (our own prompt: keep the user's language and script) → the one extracted fact | LLM judge on the fact | L2 |
| **C** | none → the utterance (verbatim) | LLM judge on the utterances | L3 |
| **D** | none → the utterance (verbatim) | bge-m3 cosine `> tau` | L4 |

**Per candidate pair** (one entry from utterance a × one from utterance b; exactly one pair per episode in every config) the harness records *input → extraction → stored text → similarity → host decision → gate → final decision* as one row of `trace.jsonl` (`dkmem_stage_trace_v1`, layout in the `dkmem/pipeline/runner.py` docstring), and one `pairwise_eval.jsonl` row per DK-Mem mode in the existing Team B schema.

- **Merge judge** (`judge.py`, prompt `merge_judge_v1`): sees only the stored text of each entry and answers `{"decision": "merge"|"keep_both", "reason": str}` strictly. It is deliberately neutral — no hint about kinship, register or names (the prompt-informed judge is a separate, unbuilt baseline). Because it never sees DK-Mem metadata, its decision is the same with the gate on or off, so it is made **once per pair and shared by all modes**; the gate is applied afterwards with `apply_gate` (incompatible → `keep_both`, underdetermined → `link_unresolved`, only when the host proposed a merge). Gate-off vs gate-on rows are therefore paired on identical extractions and judgements.
- **Config B is native-language extraction, not the Mem0 baseline.** `NATIVE_B_V1` (`native_extract.py`) is our own prompt, frozen on 2026-10-08 after the pre-freeze checks (`validation/native_b_prefreeze/REPORT.md`): one fact per utterance (`{"fact": str}`, strict parse, an empty or malformed fact is an extraction failure), Mem0's language sentence verbatim plus "do not translate" and "keep names and relationship terms exactly as written". Its system text is byte-identical to the validated candidate `native_b_candidate_v1` (the system-text sha256 is pinned in the tests). What B measures is what the extractor actually wrote: **language drift** (the fact is not in the source language), **script drift** (same language, another script, e.g. Hinglish → Devanagari) and **corruption** (garbled, invented or changed content), kept as separate quantities. The legacy Mem0 prompt (`MEM0_DEFAULT_FACTS_V1`, Mem0 0.1.x `FACT_RETRIEVAL_PROMPT`, verified identical to upstream) stays in the module for reference only; a real, version-pinned Mem0 run is a separate baseline that does not exist yet (Mem0 ≥ 2.0 has no LLM merge step).
- **Language drift vs script drift vs corruption.** `output_language_report` (classifier v2) labels each stored fact `source_language` / `translated_to_english` (= language drift, any language other than the source) / `script_changed` (= script drift) / `mixed` / `undetermined`; it compares *content words* only, so a surviving name or loanword is no longer evidence of the source language (validated: 93.4% agreement with hand labels on non-copy outputs, v1 51.2%). `extraction_checks` adds automatic *corruption signals* (`char_garble`: U+FFFD or a word mixing two scripts; `label_leak`) plus copy flags (`exact_copy`, `normalized_copy`) and `multi_sentence`. The signals are high precision and low recall (on the pre-freeze outputs: 20 of 20 flagged garbles were real, 32% of the hand-labelled garbles were caught, 21 flagged sides vs 400 hand-labelled corrupt ones), so **the corruption rate itself requires hand labels**; `summary.json` reports `stored_language` and `extraction_checks` side by side, never merged.
- **Config D** (`backends/embedding.py`): `BgeM3Embedder` (CLS pooling, L2-normalised) and `cosine_metric`, a `SimilarityMetric`. The score is the raw cosine; a negative cosine raises `SimilarityError` rather than being clipped. D requires an explicit metric and `tau` — there is no default threshold, because the right bge-m3 cutoff is an experimental result; the CLI accepts several (`--tau-d 0.80 0.85 0.90`), one group per value sharing the embeddings. A merge is proposed when `sim > tau`.
- **No threshold for the judge configs.** A, B and C have no similarity cutoff, so their `pairwise_eval` rows carry `threshold: null` (schema: `["number", "null"]`, needs Team B sign-off), `run_config.json` has `tau: null` / `tau_decides_merges: false`, passing a `tau` to them raises `ValueError`, and the similarity score (difflib placeholder unless a metric is passed) is informational only (`similarity.decisive: false` in the trace).
- **DK-Mem modes**: `off` (no distinctions, `compatibility: null`), `lexicon` (lexicon on the utterance), `lexicon+llm` (lexicon first; the V4 model's distinction only for a class the lexicon flags as ambiguous on that utterance, `resolve_distinction`; `lexicon_llm_policy` is recorded in the run config). In A the model's answer is the same V4 call that produced the gloss; in B/C/D a separate V4 call is made only for an ambiguous utterance (usually none; the 15-entry lexicon rarely produces two different values for one class) and is used only for the gate's distinctions (never stored, never shown to the judge). An ambiguous utterance whose V4 call fails has no distinction in this mode and its pair is skipped there.
- **Failures are never decisions.** A side whose extraction cannot be parsed (including an empty fact), a judge answer that is not valid JSON, and an unsupported language tag each produce a trace row with a `status` (`extraction_failed`, `judge_failed`, `unsupported_language`) and no `pairwise_eval` row in any mode, with the raw model output kept in the trace. An extraction failure is also a loss point: the row's `diagnosis.first_loss_point` is `dropped_at_extraction` (with `loss_stage` L1 for A, L2 for B, `sides_dropped`, and `lexicon_detectable_difference`).
- **Loss-point diagnosis** (`trace.py::diagnose`, in every trace row with a stored pair): runs the lexicon on the utterances and on each stored text. `first_loss_point` is `no_detectable_difference`, `storage` (the differing distinction is gone from a stored text **and the two stored texts have collapsed into the same text**: L1 in A, L2 in B), `host_merge` (the distinction survived storage, or the texts at least still differ, yet the host proposed a merge: L3 judge, L4 threshold) or `none`. `storage_state` is `visible`, `collapsed` or `distinct_not_visible` (the term was degraded but the texts still differ, e.g. *mami* glossed "mother" and *mausi* glossed "aunt"; reported as degraded, not as a storage loss). Lexicon-relative (gold labels are withheld from Team A); an attribution aid, not an FCR measurement.
- **Reproducibility**: `run_config.json` records the model (backbone, `run_info` with resolved revision, chat-template hash, versions), seed and all generation parameters, each prompt's id and sha256, the lexicon sha256, the similarity metric and embedding-model info, `tau`, the pipeline config, the input file sha256 and a hash over all per-pair input hashes (`pair_input_hash` excludes the gold entity ids), the git commit and dirty flag, and `code`: the sha256 of every `dkmem` source, schema and lexicon file (line endings normalized) with a tree hash, so a result can be tied to exact code on Kaggle where git is absent. `fingerprint` is the sha256 of everything that determines the outputs (not timestamps, git state or code hashes) and names the run group (`<config>-<backbone>-s<seed>-<fingerprint[:8]>`); with greedy decoding and the same inputs the trace is identical across re-runs. The CLI also writes `invocation.json` (the exact arguments).
- **Output layout**: `<out>/<group_id>/{run_config.json, trace.jsonl, summary.json, invocation.json}` and `<out>/<group_id>/<off|lexicon|lexicon-llm>/{run_manifest.json, pairwise_eval.jsonl}`. Strategy labels: gate on → `dk-mem-lexicon` / `dk-mem-lexicon-llm`; gate off → `mem0` (A, B), `store-surface-only` (C), `embedding-threshold` (D). `pipeline_config` in the manifest tells A from B. These labels name the host *role* in §6.3 of the plan; they do not mean the real Mem0 package is used (it is not), and for B in particular the prompt is not Mem0's.
- **Entry point**: `python -m dkmem.pipeline.cli` (see `DKMEM_FIRST_RUN.md` for the exact first-run command). The sanctioned Tier 1 file is hash-checked; another `--input` (e.g. the week-1 pilot pairs) is accepted and recorded as `sanctioned: false`. `--shard` splits an LLM that does not fit one T4 (Qwen2.5-7B) over both GPUs (`HFGenerator.load_sharded`). `validation/abcd_first_run/build_kernel.py` builds the Kaggle notebook that runs the unit-test suite and then this command.

Not part of this harness: the real Mem0/A-Mem packages, A-Mem, and multi-seed aggregation. The other baselines and FCR/MCR are in §13c. For Config D the τ sweep is done offline from `similarity_score` (the host decision is `sim > tau`, and the gate's effect depends only on the distinctions), as `pairwise_eval.schema.json` already assumes; the judge configs have no τ to sweep.

---

## 13c. Baselines and offline evaluation — `dkmem/baselines/`, `dkmem/eval/`

Details, exact commands and the unresolved choices are in `DKMEM_BASELINES.md`; this section is the map.

- **Prompt-informed merge judge** (`merge_judge_informed_v1`, sha256 `614f2331…`). `merge_judge_v1` (sha256 `3855ef65…`, unchanged) plus one paragraph that explains cross-lingual distinctions and tells the judge to weigh them as evidence. It is advice, not a rule: there is no "always keep both" wording, so it is not a hard cannot-link constraint (that is the DK-Mem gate). The system text before the paragraph, the two chat examples and the output format are byte-identical to v1. It runs through the A–D harness (`--judge-prompt merge_judge_informed_v1 --modes off`); the gate-off rows get the strategy `prompt-informed-judge`. The prompt id and hash enter `run_config.json` and the fingerprint.
- **Mem0 OSS v1.0.11** (`dkmem/baselines/mem0/`). Tag `v1.0.11` = commit `144627c4…`. The package is not imported: three upstream files (`memory/main.py`, `configs/prompts.py`, `memory/utils.py`) are vendored as `.py.txt`, pinned by sha256 and git blob id (the blob ids equal what GitHub reports for the tag), and verified before use; the prompts and helper functions are executed from them (with the prompt's `datetime.now()` date frozen to 2026-10-07). `Mem0Memory.add` re-implements `Memory._add_to_vector_store` for `infer=True`: one extraction call (`USER_MEMORY_EXTRACTION_PROMPT`, "record the facts in the same language"), per-fact search (`limit=5`, no threshold), id remapping to `"0".."n"`, one update call (`DEFAULT_UPDATE_MEMORY_PROMPT`), sequential ADD/UPDATE/DELETE/NONE with per-action error guards, history rows, and upstream's silent failure behaviour. Substituted: Qwen as the LLM (`response_format` cannot be enforced), bge-m3 as the embedder, in-memory vector store and history. A Tier 1 episode is two `add` calls on a fresh memory; `events.classify_pair` maps b's events to `supersede` (UPDATE/DELETE of a's memory), `keep_both` (a new memory stored), `merge` (NONE for a's memory and nothing stored), `no_entry` (an utterance gave no facts) or `host_failed` (the update step was unusable). Output: an A–D-shaped group with the single mode `off`, strategy `mem0`, and a trace holding the raw LLM input/output, retrieval hits, id mapping, every action and the history rows.
- **Never-merge / flat dense RAG** (`dkmem/baselines/flat.py`). `NeverMergeHost` in the normal `consolidate` write path, bge-m3 retrieval and the standard export: every utterance is stored verbatim, nothing is consolidated, pairwise FCR is 0 by construction (strategy `flat-dense-rag`, `backbone: null`). For Tier 2 the same store ingests a conversation (`ingest_conversation`, host-agnostic), retrieves (`FlatRAG.retrieve`, `retrieval_report`) and answers questions (`answer_questions`, prompt `flat_qa_v1`). The Tier 2 `Turn`/`Question` records are a provisional shape: they were written before the Tier 2 data package (`eval/tier2/data/`, §13d) existed and have not been checked against it.
- **FCR / MCR** (`dkmem/eval/metrics.py`) exactly as `tier1_eval_contract.md` §4–6: union-find over `entry_id`, denominators are all gold pairs (not-compared and no-entry pairs count as not merged), `link_unresolved` is not merged. The gold relation comes from Team B's key (`dkmem/eval/gold.py`, passed explicitly); the opaque entity ids in the sanctioned input are all distinct and are not labels.
- **Raise-τ** (`dkmem/eval/sweep.py`). Config D only: from the logged bge-m3 cosines, every distinct score plus one point below the smallest, the host decision `score > tau`, then `apply_gate` with the logged distinctions, for each DK-Mem mode — so `off` is raise-τ and `lexicon` / `lexicon+llm` are DK-Mem on the same host. Validated against real harness runs at ten τ values in the tests. Judge groups are refused: no probability/logit thresholding is implemented. Matched-MCR comparison: `best_fcr_at_mcr`, `compare_at_matched_mcr`.
- **DK-Mem ablation** (`dkmem/eval/ablation.py`): per group, lexicon-only vs lexicon+LLM FCR/MCR, gate activity (vetoes, unresolved links), extra LLM calls (0 for lexicon-only), the effect of the model fallback, and the paired-input invariants (same similarity score, stored texts and surface across modes).
- **Fairness** (`dkmem/eval/fairness.py`): reads the `run_config.json` of any set of groups and reports differing inputs, pair order, seed, backbone/revision, decoding (batch size is a note), embedder and similarity metric, lexicon hash.
- **Commands**: `python -m dkmem.baselines.cli {mem0,flat}`, `python -m dkmem.eval.cli {score,sweep,compare,ablation}`, `python -m dkmem.pipeline.cli --judge-prompt …`. `validation/abcd_first_run/build_kernel.py` can build the Kaggle notebook for each (`--baseline`, `--judge-prompt`, `--embedding-revision`) and now embeds `.txt` files (the vendored Mem0 sources).
- `strategy` values added to what `PairwiseEvalRecord` accepts (`dkmem/tier1/io.py`): `prompt-informed-judge`, `flat-dense-rag`, `raise-tau`; they were already in the schema enums. `raise-tau` is not emitted by any runner yet: the sweep is offline and writes no `pairwise_eval` rows.

---

## 13d. Tier 2: injected multi-session conversations, `eval/tier2/`

Status on 2026-10-14: **the full Tier 2 experiment has run on both arms** (v1.0 and mirror v1.1m; Configs C and D, gate off/lexicon; seed 0; 8 runs, all passing the contract). Results are single-seed, rest on provisional labels and are not a demonstration that DK-Mem solves false consolidation. Everything under `eval/` and `validation/tier2_*` is untracked in git (not yet committed). Tier 2 label files are git-ignored (`.gitignore`), and so are the run outputs under any `runs/` directory, by the generic `runs/` rule.

### Completed work

- **Benchmark v1.0** (`eval/tier2/data/`, pinned by `FROZEN_v1.0.json`; described in `eval/tier2/README.md`): 69 conversations × 6 sessions, one injected pair each (42 gold-different, 27 gold-same; kinship, honorific_register, name_variant), 111 QA questions. Labels come by construction from the provisional Tier 1 gold. The system receives only the conversations, the questions (read after consolidation) and an opaque turn → entity-id passthrough. Gold, QA references and injection metadata are evaluator-only.
- **Runner** (`run_tier2.py`, `memory_store.py`): a persistent per-conversation store (union-find memory records; non-destructive, members joined with `" | "`) and shared bge-m3 top-5 candidate retrieval over all earlier raw entries. Configs C (LLM judge) and D (cosine `> tau`, τ 0.90 as a run-level execution value), each with gate `off`/`lexicon` (`apply_gate` veto). QA uses a fixed answerer prompt (`tier2_qa_v1`). Outputs follow the Tier 1 schema (`dataset_tier: tier2_injected_sessions`) plus sidecars: retrieval log, final store, QA answers, judge log, run info.
- **Contract and validation** (`contract.py`): validates a run against the benchmark arm's FROZEN file, the exact passthrough file the run used, and the evaluator-side QA-id map (questions in Kaggle payloads carry opaque ids). It maps each injected pair to `merged` / `not_merged` / `retrieval_miss` / `judge_parse_error` from the **direct** record and reports `same_final_memory_record` separately. `judge_provenance.py` labels which judge a run used.
- **History (kept unchanged).**
  - The first full Tier 2 run (`eval/tier2_full_runs/`, 2026-10-08; provisional reports in `eval/results/`) used a harness judge that shared the id `merge_judge_v1` but not the text (sha256 `f0dc9cf7…`, 32-token budget). Its Config C is labelled invalid as Tier 1 C: 3105/3105 answers were "different".
  - The fix (the frozen Tier 1 judge from `dkmem`, 128 tokens) was smoke-tested on 2026-10-13 (`eval/tier2_smoke_runs/t2frozen_smoke_20261013/`). The frozen "same fact" judge answered `keep_both` on 135/135 pairs, because every Tier 2 pair states different facts, so Config C was uninformative under that judge.
- **Mirror arm v1.1m** (`eval/tier2/mirror_v1_1/`, frozen 2026-10-14T05:15Z). In v1.0, attribute pattern predicts the label: all 42 gold-different pairs share an attribute with different values; all 27 gold-same pairs differ in attribute. The mirror arm is the same 69 conversations with only member b's sentence replaced: gold-different → a different attribute; gold-same → the same attribute with a conflicting value. Labels, markers, positions and distractors are v1.0's. Combined with v1.0, relation is balanced against attribute pattern in every class × relation stratum. It has no QA. `validate_mirror.py` passes 853/853 checks. It is built from v1.0 data without reading the Tier 1 key.
- **Config C judge, identity policy** (`judge_entity.py`): merge = the same specific person/thing/event, even with different or conflicting facts (both texts kept); keep_both = different entities, user-only overlap, or identity not supported. It has no language, kinship, register or script hint. Same strict parser and 128-token budget as Tier 1. Each validation set, its criteria and its scorer were frozen before any model run on it (`judge_validation*/FREEZE.json`). The 8 gates are identical across all three validations; probe classes are reported, not gated.

| Validation (77 cases × 2 orders) | Prompt / model | Merge recall | Keep recall | Conflict | Ambiguous | Order | Attribute-shortcut (worst cell) | Result |
|---|---|---|---|---|---|---|---|---|
| `judge_validation/` (frozen 05:10Z) | `merge_judge_entity_t2_v1` / 3B | 0.44 | 1.00 | 0.60 | 1.00 | 0.89 | 0.10 | **failed** |
| `judge_validation_v2/` (new set, 05:39Z) | `merge_judge_entity_t2_v2` (`36146ec0…`) / 3B | 0.846 | 0.85 | 0.85 | 0.69 | 0.81 | 0.71 | **failed** (22/154 reasons contradict the decision) |
| `judge_validation_7b/` (new set, 06:05Z) | same v2 prompt / Qwen2.5-7B `a09a3545…`, sharded | 1.00 | 0.983 | 1.00 | 1.00 | 0.984 | 0.96 | **passed** (0 contradictions, 0 parse failures) |

  Outputs and scored reports: `eval/tier2_entity_runs/judge_{validation,v2_validation,v2_7b_validation}_20261014/`. Probes on the 7B: kinship kept apart 8/8; same name in two scripts merged 6/6; German du/Sie kept apart 0/4.
- **Separate judge and QA models** (`run_tier2.py`): `--judge-model-id/--judge-model-revision/--judge-shard/--judge-max-memory/--judge-device` and `--qa-device`. Default is unchanged: the QA model judges. C manifests record the judge's own backbone, run info, layer map and tokenizer, plus QA's run info for every config. Kaggle notebooks are built by `validation/tier2_entity/build_kernels.py`. The memory probe (`judge_validation/memory_probe.py`, `eval/tier2_entity_runs/memory_probe_20261014/`) loaded 3B QA on `cuda:0`, the 7B sharded with caps `0=5GiB,1=11GiB` (7/25 layers) and bge-m3. Peak allocated was 13.34 GiB (GPU 0) and 11.64 GiB (GPU 1) of 14.56; minimum driver-free was 0.90 GiB on GPU 0. Its 154 judge outputs were byte-identical to the 7B validation run.
- **Smoke tests on Kaggle** (3 conversations per arm, seed 0; run before the full experiment):
  - **Config D only:** `eval/tier2_entity_runs/d_smoke_{v10,mirror}_20261014/`, 4 runs.
  - **Combined C + D:** `eval/tier2_entity_runs/cd7b_smoke_{v10,mirror}_20261014/`, 8 runs: C:off, C:lexicon, D:off, D:lexicon × 2 arms. C uses the v2 judge on the 7B, separate from the QA model; QA is Qwen2.5-3B `aa8e7253…` in every run.
  - **Checks:** all notebook acceptance checks true. The contract passes all 12 runs (0 errors, 0 warnings) with the exact passthrough, QA-id map and arm-specific FROZEN file. Each output directory has a `MANIFEST.json`.
- **Frozen analysis plan** (`analysis_plan_full_v1.md`, implemented by `entity_report.py`). `ANALYSIS_PLAN_FREEZE_v1.json` pins both, plus `contract.py` and `generate_tier2.py`; it was frozen at 2026-10-14T07:42:29Z, before any full-run output existed.
- **Official entry point for entity reports: `python -m tier2.entity_report_verified`** (decided; the analysis plan is NOT re-frozen and `entity_report.py`, `contract.py` stay byte-identical). It re-verifies every run first (per-row judge identity, strict re-parse of each raw judge output, embedder revision against `embedder_pin.BGE_M3_REVISION`), writes no report if a run fails (unless `--allow-excluded`), runs the unchanged pinned report, and writes a `<out>.verification.json` sidecar. For the 8 stored full runs it regenerates `TIER2_FULL_entity_report_v1.json` byte-for-byte. Calling `tier2.entity_report` directly is still possible and is not protected.
  - **Primary:** direct-pair FCR/MCR. A pair counts as merged only if the record between the two injected entries is a merge; retrieval misses and parse errors count as not merged.
  - **Secondary:** final-memory-record outcomes, and the number of pairs joined only through intermediate entries.
  - **Diagnostics:** distractor–distractor and injected–distractor merge rates, gate vetoes bypassed through intermediate merges, and QA split by whether the supporting memory was retrieved.
  - **Intervals:** Wilson 95% for pair-level proportions; a conversation-cluster bootstrap for comparison-level rates and QA; paired bootstrap plus exact McNemar for contrasts (B = 10 000, seed 20261014, no multiplicity correction).
- **Batch-composition diagnostic** (`judge_validation/batch_diagnostic.py`; `eval/tier2_entity_runs/batch_diagnostic_20261014/`). The 135 v1.0 smoke judge calls were re-judged on the 7B in three batchings:
  - **in-situ:** reproduced the smoke judge log byte for byte (135/135);
  - **batch size 1 and batch size 8:** gave the same decision on all 132 non-injected pairs (132/132). The raw reason wording differed in 3 and 2 calls respectively.
  - The four user-only merges occur under every batching.
- **Full Tier 2 run.**
  - **Kernels:** `validation/tier2_entity/kernel_cd7b_full_{v10,mirror}`. Their payload trees equal the smoke-tested kernels' (`05b61138…` and `17bfa483…`). They passed `--check`, an independent payload inspection and a fake-model dry run over all 69 conversations.
  - **Outputs:** `eval/tier2_entity_runs/cd7b_full_{v10,mirror}_20261014/`, each with a `MANIFEST.json` of 136 files.
  - **Analysis:** `eval/tier2_entity_runs/TIER2_FULL_entity_report_v1.json` (sha256 `18b5d9df…`). It holds per-pair gold relations, so it is evaluator-side.
  - **Checks:**
    - all notebook acceptance checks are true on both arms;
    - all 8 runs pass the contract (0 errors, 0 warnings);
    - the judge was the pinned 7B, separate from QA, which was the pinned 3B in every run;
    - each C run made 3105 judge calls with 0 parse failures, 0 truncated and 0 reason–decision contradictions.
  - The first v1.0 download was truncated; a forced re-download was verified (all files parse; record counts equal the kernel's own summary).

### Full-run results (69 pairs per arm: 42 gold-different, 27 gold-same; seed 0; descriptive)

FCR = gold-different pairs merged / 42; MCR = gold-same pairs not merged / 27 (direct pair; 95% Wilson interval). In all 8 runs the final-memory-record outcomes equal the direct outcomes. There were 0 pairs joined only through intermediate entries, 0 retrieval misses and 0 judge parse errors.

| Run | v1.0 FCR | v1.0 MCR | mirror FCR | mirror MCR |
|---|---|---|---|---|
| C, gate off | 15/42 = 0.357 [0.230, 0.508] | 0/27 = 0.000 [0.000, 0.125] | 11/42 = 0.262 [0.153, 0.411] | 1/27 = 0.037 [0.007, 0.183] |
| C, gate lexicon | 7/42 = 0.167 [0.083, 0.306] | 5/27 = 0.185 [0.082, 0.367] | 9/42 = 0.214 [0.117, 0.359] | 6/27 = 0.222 [0.106, 0.408] |
| D (τ 0.90), gate off | 5/42 = 0.119 [0.052, 0.250] | 27/27 = 1.000 [0.875, 1.000] | 0/42 = 0.000 [0.000, 0.084] | 27/27 = 1.000 |
| D (τ 0.90), gate lexicon | 5/42 = 0.119 | 27/27 = 1.000 | 0/42 = 0.000 | 27/27 = 1.000 |

- **Config C is too permissive in some cases.**
  - Gate-off false merges on v1.0: German register 6/6, kinship 8/32, name variant 1/4. On the mirror arm: 6/6, 2/32 and 3/4.
  - It merged nearly all gold-same pairs: MCR 0/27 on v1.0 and 1/27 on the mirror arm.
  - It merged 146/2266 (v1.0) and 148/2281 (mirror) distractor–distractor comparisons, about 6.4–6.5%. Of these, 113 and 114 carried the reason "A is about the user; B is about the user".
  - Injected–distractor merges were 17/770 and 14/755 with the gate off.
  - Its decisions changed little between arms on the same source pairs. Gate off, mirror − v1.0: gold-different −0.095 [−0.214, +0.024], gold-same −0.037. So the judge does not appear to follow the attribute-pattern shortcut. This is a tentative reading from one seed.
- **Config D is too conservative in the tested setup.**
  - At τ 0.90 it never merged a gold-same pair (MCR 1.0 on both arms).
  - Its only merges were 5 of the 6 German register gold-different pairs on v1.0. It merged nothing on the mirror arm, where the changed attribute lowered those pairs' cosine (mirror − v1.0: −0.119 [−0.214, −0.024], McNemar p = 0.0625).
  - τ 0.90 is a run-level execution value, not a tuned operating point. D's low FCR comes with no merging at all, not with discrimination.
- **The lexicon gate reduces some false merges but also blocks correct ones.**
  - In C on v1.0 it removed all 8 kinship false merges (FCR 0.357 → 0.167; paired difference −0.190 [−0.310, −0.071], McNemar p = 0.008). But it also blocked 5 of the 7 Hindi register gold-same pairs (the register shift read as incompatible), raising MCR from 0 to 0.185.
  - On the mirror arm: FCR 0.262 → 0.214 and MCR 0.037 → 0.222.
  - It could not veto the German du/Sie false merges, because the lexicon has no German entries.
  - In D it vetoed nothing: D's only host merges (the 5 German pairs on v1.0) were lexicon-compatible.
  - 25 (v1.0) and 18 (mirror) C vetoes were issued, and none was bypassed through intermediate merges.
- **QA (v1.0 only; the mirror arm has no QA, so QA is not compared across arms).**
  - Accuracy: C off 90/111 = 0.811, C lexicon 91/111 = 0.820, D 91/111 = 0.820 (cluster-bootstrap intervals about ±0.07).
  - 9 forbidden-alias hits per run.
  - The supporting memory was retrieved for 109–111 of 111 questions.
  - QA does not separate the configurations at this sample size.

### Observed results (smoke level; 3 injected pairs per arm, not an evaluation)

- **Config C (7B judge):**
  - 135 judge calls per run: 0 parse failures, 0 truncated, output ≤ 35 tokens. C:off and C:lexicon judge outputs are byte-identical, and the gate vetoed nothing.
  - Injected pairs in both arms:
    - German du/Sie pair (gold different): **merged**; the gate reports `compatible` because the lexicon has no German entries.
    - Hindi nani/dadi (gold different): kept apart; the gate reports `incompatible`.
    - Priya / प्रिया (gold same): merged, including with conflicting birthdays in the mirror arm.
- **Config D:** 0 merges in all runs (max cosine 0.876 on v1.0 and 0.843 on the mirror arm, below τ 0.90). Gate verdicts were 121 compatible, 13 underdetermined, 1 incompatible. v1.0 D reproduces the 2026-10-13 smoke.
- **Retrieval:** every injected pair was compared, so there were no retrieval misses.
- **QA (v1.0 arm only):** C 4/5, D 3/5 correct. The difference is the merged German pair, whose two questions were then both answered correctly.

### Known limitations

- **User-only distractor over-merging (Config C, 7B).**
  - 4 of 100 distractor–distractor comparisons per C run were merged with the reason "A is about the user; B is about the user; same entity". Examples: "Ich muss morgens früh aufstehen" ↔ "Ich gehe oft spazieren"; "Aaj traffic mein bahut time laga" ↔ "Aajkal main roz walk par jaata hoon".
  - **Audit: no implementation defect identified.**
    - The payload code is byte-identical to the repository.
    - The judge saw the verbatim turn texts, with the frozen v2 prompt on every call.
    - Proposals equal the strict parse of the raw output, and record decisions follow proposal plus gate.
    - Final memory records equal the union-find of the merge records.
  - **Validation coverage gap:** the 12/12 user-only validation calls were events or plans with distinct objects. The validation set had no pair of two different routines. The same reason string also accompanies correct same-fact merges about the user, the pattern the prompt's coffee example teaches.
  - **Hypothesis, not tested:** routine statements fall between that example and the user-only rule.
  - **Tested (batch diagnostic):** batch composition does not cause these merges (132/132 identical decisions at batch sizes 1 and 8).
  - **Full run:** the pattern persists at scale, at about 6.4–6.5% of distractor–distractor comparisons in C (see the full-run results above).
- **Transitive (indirect) contamination.** Merges are transitive (union-find), and the judge and the gate only see raw entry pairs. Entries can therefore share a memory record through an intermediate entry, and a per-pair gate veto can be bypassed this way. This matches the Tier 1 cluster-path definition of "merged".
  - **Smoke runs:** it did not occur (injected–distractor merges 0/32 per C run).
  - **Full run:** it did not occur either. 0 injected pairs were joined only through intermediate entries, and 0 gate vetoes were bypassed. The risk remains for other data.
- **Single seed; provisional labels; no native-speaker validation yet.** All Tier 2 numbers come from one run per configuration (seed 0). Gold labels are by construction from the provisional, LLM-annotated Tier 1 gold, and no native speaker has reviewed the Tier 2 benchmark or the judge-validation sets.
- **Class and label are confounded.** In both arms, kinship pairs are all gold-different and Hindi register pairs all gold-same; German register pairs are all gold-different, and name variant has only 4 gold-different pairs. A class effect cannot be separated from a relation effect.
- **Comparability.** The judge backbone (7B) differs from Tier 1 Config C (3B): Tier 2 C results are not comparable with Tier 1 C.
- **German du/Sie.** The 7B judge treats du/Sie as one person, which is a false merge under the benchmark's contested two-addressee convention. The lexicon cannot veto it.
- **Mirror arm.** Class × relation × language stay confounded, as in v1.0. The arm has no QA. Changing the attribute shifts cosine, so retrieval must be reported per arm. The six German replacement sentences are hand-written.
- **Labels and authorship.** The validation sets were written by Claude, without native-speaker review. Labels inherit the provisional, LLM-annotated Tier 1 gold.
- **GPU 0 headroom.** It is small (0.90 GiB at the probe's worst case; real QA prompts are shorter).
- **Offline audit.** `eval/tier2/audit_offline.py` (Config D sweep) reads the Tier 1 key and expects the 69-conversation v1.0 layout. Its test (`eval/tests/test_tier2_audit_offline.py`) errors without the key at `eval/teamB_answer_key.jsonl`.

### For the label audit (benchmark revision)

- **What to audit.** Each v1.0 pair has two member sentences (`banks/pair_specs.json`: markers, facts, QA) and a gold relation (`data/tier2_gold.jsonl`). Both are inherited from the provisional Tier 1 gold.
- **Contested design assumptions** (also in `eval/tier2/README.md`):
  - the 4 name-variant gold-different pairs are read as two different people;
  - the 6 German register pairs are read as two addressees told apart by du vs Sie;
  - the 7 Hindi register gold-same pairs treat a register shift (tu/tum/aap) as the same addressee.
  - The full-run decisions on these strata are the least reliable.
- **Where the files are.** Labels, injection metadata, QA references and pair specs (both arms) are git-ignored and evaluator-only; they are shared outside git. The mirror arm reuses v1.0's labels on rewritten member-b sentences (`mirror_v1_1/banks/pair_specs_mirror.json`).
- **Rules.**
  - Do not edit any file pinned by `FROZEN_v1.0.json`, `FROZEN_v1.1m.json` or a `FREEZE.json`.
  - A revised benchmark should be a new version with its own data directory and FROZEN file, so the completed v1.0/v1.1m results stay reproducible.
  - `generate_tier2.py` and `validate_tier2.py` read the Tier 1 key; `validate_mirror.py` does not.

### Pending decisions and next steps

- **Label audit and revised benchmark** (Member 2). The results above should be re-read against any revised labels; nothing in this section is conclusive until then.
- **Git.**
  - Commit the Tier 2 code and data that are safe to share; the evaluator-only files stay out of git.
  - Add ignore rules before staging, because these are not yet ignored:
    - `eval/tier2_entity_runs/TIER2_FULL_entity_report*.json` (per-pair labels);
    - `eval/tier2_full_runs/*/pairwise_eval.jsonl` (ids that join to the Tier 1 key);
    - `validation/tier2_entity/kernel_*` and `*.evaluator/` (generated; QA-id maps);
    - the `src/` snapshots in the output directories.
- **Missing documentation.** There is no human-readable Tier 2 results report besides this section and the evaluator-side JSON, and no `mirror_v1_1/README.md`.

### Tests and reproducibility checks

- **Test suites.** `tests/test_tier2_judge.py`, `tests/test_tier2_smoke_payload.py` and `tests/test_tier2_entity.py` (45 tests) are in the root suite: 889 tests, OK, 2 skipped (last run 2026-10-14). The suite uses fake models only and never reads the Tier 1 key. `eval/tests`: 69 tests run, 1 error: the class setup of `test_tier2_audit_offline` needs the Tier 1 key at `eval/teamB_answer_key.jsonl` (key-holder only).
- **Integrity checks (verified 2026-10-14):**
  - every pin in `FROZEN_v1.0.json` and `FROZEN_v1.1m.json` matches;
  - the three judge-validation freezes and `ANALYSIS_PLAN_FREEZE_v1.json` verify;
  - all 13 output `MANIFEST.json` files (historical and new) verify unchanged;
  - `validate_mirror.py` passes 853/853;
  - `build_kernels.py --check` is fresh for both full kernels.
- **Model pins:** QA Qwen2.5-3B `aa8e7253…`, judge Qwen2.5-7B `a09a3545…`, bge-m3 `5617a9f6…`, all recorded in every run manifest. The Kaggle logs came back empty.

---

## 14. Actual runs on disk — `tier1_results/`

Six completed, real runs exist (dated 2026-09-30); the two `dk-mem-lexicon-llm` strategies used Qwen2.5-3B-Instruct, the `dk-mem-lexicon` ones no model. **They predate the scope alignment** (prompt v1, the old seven-class scope, the 16-entry lexicon incl. Turkish evidentiality) and were not regenerated:

| Run directory | Strategy | Seed | Backbone | Rows in `pairwise_eval.jsonl` |
|---|---|---|---|---|
| `dk-mem-lexicon_seed{0,1,2}` | `dk-mem-lexicon` | 0,1,2 | `null` | 173 / 173 |
| `dk-mem-lexicon-llm_seed{0,1,2}` | `dk-mem-lexicon-llm` | 0,1,2 | `Qwen/Qwen2.5-3B-Instruct` | 138 / 173 |

The lexicon-only strategy produced a comparison row for every one of the 173 episodes. The LLM-assisted strategy produced rows for only 138 — the other 35 episodes failed `ExtractionError`/`ValueError` on at least one side and were correctly emitted as nothing (per §13), not as fabricated or crashed records.

No FCR/MCR/κ scoring exists in this repository — these six runs are the raw deliverable Team B scores externally (see §16).

**Consequences of the scope change for these files** (checked, nothing in `tier1_results/` was modified):
- Their manifests still validate. Of 933 pairwise rows, **135 contain a now-out-of-scope `distinction.class`** (evidentiality, classifier, politeness, deixis) and no longer validate against the narrowed `pairwise_eval.schema.json`.
- Re-running `dk-mem-lexicon` in memory on the same 173 records with the current code changes exactly **10 rows** — the 10 Turkish records, whose evidential suffix is no longer extracted (7 go `underdetermined_link` → `merge`, 3 → `no_merge`). Every other row, and every `similarity_score`, is byte-identical.
- The current Tier 1 v2 file is not re-scoped: per `tier1_eval_contract.md` only kinship (32 pairs), honorific_register (13) and name_variant (24) pairs — 69 of 173 — are in the current scope, kinship has no same-entity controls, and its labels are LLM-annotated. A new probe set is Team B's work.

---

## 15. Worked example: *chachi* vs. *mausi* (real data, not hypothetical)

Record `ep_27b02ab5a187` in the real Tier 1 input:
```
utterance_a: "meri chachi Pune mein rehti hai"   (chachi = father's younger brother's wife)
utterance_b: "meri mausi Pune mein rehti hai"    (mausi  = mother's sister)
```
Both are real lexicon entries (§7): different people, same English word ("aunt").

### `dk-mem-lexicon` (no LLM) — actual output, seed 0
```json
entry_a.gloss = "meri chachi Pune mein rehti hai"   (= raw surface, no translation)
entry_b.gloss = "meri mausi Pune mein rehti hai"
entry_a.distinction = {"kinship": "chachi"}
entry_b.distinction = {"kinship": "mausi"}
similarity_score = 0.8852459016393442
threshold        = 0.85
compatibility    = "incompatible"
decision         = "no_merge"
```
The two surface strings differ by only one word out of five, so the character-level ratio is high (0.885) and — note — **above** τ (0.85). Without gating, this pair would have been merged. The gate catches it: `kinship` is marked on both sides with different values (`chachi` ≠ `mausi`) → `incompatible` → forced `no_merge`, regardless of the (already-high) similarity.

### `dk-mem-lexicon-llm` (Qwen2.5-3B-Instruct, prompt v1) — actual output, seed 0
```json
entry_a.gloss = "user's grandmother lives in Pune"
entry_b.gloss = "user's grandmother lives in Pune"
entry_a.distinction = {"kinship": "chachi"}   (lexicon override)
entry_b.distinction = {"kinship": "mausi"}    (lexicon override)
similarity_score = 1.0
threshold        = 0.85
compatibility    = "incompatible"
decision         = "no_merge"
```
Here Qwen's own translation is actually wrong (*chachi*/*mausi* are "aunt", not "grandmother" — a real extraction error, not a cherry-picked example), and both utterances were translated to the *identical* English gloss, giving `similarity_score = 1.0` — the exact silent-false-consolidation setup the research idea describes. The lexicon overlay still correctly tagged `kinship: chachi` / `kinship: mausi` from the raw surface text (the lexicon scans `extraction.surface`, which is unaffected by the translation error), so the gate still catches the conflict and blocks the merge. This is a real, on-disk illustration of exactly why the gate is checked independently of whatever the gloss says.

---

## 16. Implemented vs. not implemented

| Component (from `DKMEM_NEW_RESEARCH_IDEA.md`) | Status |
|---|---|
| Dual-field extraction (`gloss` + `distinction` + `surface` + `lang_profile`) | **Implemented** (§6, §9) |
| Lexicon-first, model-second cascade | **Implemented** (§9) |
| Lexicon-only ablation (zero LLM calls) | **Implemented** (§13, `dk-mem-lexicon`) |
| Merge gating: `compatible()` with incompatible/underdetermined/compatible | **Implemented** (§12) |
| Gate as a veto in front of a host merge mechanism (`apply_gate`) | **Implemented** (§12) and used in front of the judge / threshold hosts of §13b |
| Pluggable similarity separated from the gate | **Implemented** (§11) |
| Vocabulary for configurations A–D and DK-Mem off / lexicon / lexicon+llm | **Implemented** (`dkmem/config.py`, manifest fields); the harness that runs them is §13b |
| `supersede` (recognizing an update, not a duplicate) | **Not implemented** — schema value exists; `apply_gate` can veto a host's `supersede`, nothing here produces one |
| Read-side distinction-aware disambiguation (query selects among entries) | **Not implemented** — no retrieval/query code exists anywhere in the repo |
| A persistent, queryable memory store across utterances/episodes | **Implemented for Tier 2 only** (`eval/tier2/memory_store.py`, §13d: per-conversation, non-destructive union-find records). Tier 1 still resets per episode (§13); `dkmem/store/` is not described here |
| FCR / MCR / FCR–MCR frontier computation | **Not implemented here** — Team B computes this externally from `pairwise_eval.jsonl` |
| Real embedding similarity (bge-m3) | **Implemented and run on GPU** (revision `5617a9f6…`): Config D of the full Tier 1 A–D run (`results/full_ad_3b_s0_20261010/`) and the Tier 2 runs (§13d). Tier 1 runs 1–6 still use the `DIFFLIB_RATIO` stand-in |
| Configurations A–D: English-forced extraction + judge (A), native-language extraction (`native_b_v1`) + judge (B), verbatim + judge (C), verbatim + bge-m3 threshold (D), each with DK-Mem off / lexicon / lexicon+llm, with a per-pair stage trace | **Implemented** (§13b), tested with fake models, a 20-record Qwen2.5-3B smoke test of A–C (`validation/smoke_abc/`) and the 173-record × 1.5B/3B/7B check of the B prompt (`validation/native_b_prefreeze/`) — a full 173-record A–D run on Qwen2.5-3B, seed 0, exists in `results/full_ad_3b_s0_20261010/` (key-free counts; scoring needs Team B's key; not summarised here). Not implemented: real Mem0/A-Mem packages |
| Baselines: Mem0 (two prompts), A-Mem, store-surface-only, embedding-threshold, raise-τ, prompt-informed judge, flat dense RAG | **Implemented, never run on a real model** (§13c): a pinned Mem0 v1.0.11 reproduction (one prompt: Mem0's own default, which is not English-forced), the prompt-informed judge, the offline raise-τ sweep and the never-merge / flat-RAG control. The gate-off runs of Configs A–D remain the host-only rows for store-surface-only (C) and embedding-threshold (D) and use this repo's own prompt and judge. **Not implemented: A-Mem (dropped), LightMem (dropped), a Mem0 variant with an English-forced extraction prompt** |
| FCR / MCR, the FCR–MCR frontier, fairness check | **Implemented offline** (`dkmem/eval/`), needing Team B's gold key; tested on synthetic data only |
| Kinbank-generated kinship lexicon, name-variant entries | **Not implemented** — the lexicon is 15 Hindi entries |
| Tier 2 (injected multi-session conversations) | **Implemented and run once** (§13d): benchmark v1.0 + mirror arm v1.1m, runner, contract, Config C identity judge (validated on Qwen2.5-7B) and Config D (τ 0.90), gate off/lexicon. Full experiment on both arms, 2026-10-14, seed 0, provisional labels; label audit pending |
| Tier 3 (one non-Indic kinship slice) | **Not implemented** — no non-Hindi lexicon entries; the `dataset_tier` enum value exists but no Tier 3 input/runner |
| Memory bloat measurement | **Not implemented** |
| Backbone sweep (1.5B/3B/7B) | **Not implemented** — the A–D runs use Qwen2.5-3B-Instruct; Qwen2.5-7B is used only as the Tier 2 Config C judge (§13d) and in the Config B pre-freeze check |
| Human-adjudicated gold labels for Tier 1 | **Not applicable yet** — current labels are explicitly "LLM-annotated, provisional" per the handoff docs |

---

## 17. Known limitations / gaps worth tracking

1. **The lexicon is small and Hindi-only.** The gate checks `kinship` and `register`, and the lexicon (§7) has 12 Hindi kinship terms and 3 Hindi register pronouns. Nothing covers other languages (German *du*/*Sie*, a non-Indic kinship slice for Tier 3) and `name_variant` has no entries; in the no-LLM strategy those can never be marked. Coverage has not been measured against any independent source.
2. **The default similarity is a character-level string metric, not a semantic one.** `DIFFLIB_RATIO` is explicitly a placeholder for a real embedding model (§11) and will behave oddly on paraphrases that are semantically identical but lexically different, or on strings that happen to share many characters without sharing meaning. `DEFAULT_TAU = 0.85` is tied to it.
3. **Only one entity per side is extracted by the DK-Mem extractors.** `extract_lexicon_only`/`dkmem_extract_many` give one `Extraction` per utterance side. Only Config B can produce several entries per side (one per Mem0 fact), each carrying the utterance-level distinctions.
4. **The LLM extractor can mistranslate kinship terms outright** (§15's real example: *chachi*/*mausi* → "grandmother" instead of "aunt"), which is exactly the scenario that makes the gate's independence from the gloss valuable — but it also means `gloss`-based retrieval (not implemented, but implied by the design) would be unreliable whenever this happens.
5. **35 of 173 episodes (≈20%) produce zero comparable entries in the LLM strategy** (§14) — either side's extraction failed validation. This is handled correctly (emit nothing, don't crash), but it also means roughly a fifth of the benchmark currently contributes no signal for the LLM-assisted strategy.
6. **No code enforces that `dk-mem-lexicon` and `dk-mem-lexicon-llm` use identical non-backbone settings**, as the external run-instructions contract requires (`teamA_tier1_run_instructions.md` §5) — this is a reporting/process obligation on whoever runs the experiments, not something `dkmem/tier1/runner.py` checks in code.
7. **`DISTINCTION_CLASS_TRANSLATION`'s one-key-only serialization** (§13) means an utterance that marks two distinction features simultaneously only reports one externally, even though the gate internally used both — a known, documented asymmetry between what gates the decision and what's visible in `pairwise_eval.jsonl`.
8. **Prompt v4 is untested.** It is v3 re-scoped, but it has not been run on Qwen; the 7/20 → 10/20 development-set result belongs to v2/v3. Known remaining model errors on that set (e.g. *chachi* glossed as "grandmother", wrong name script, *aunty* tagged as kinship) are not addressed by the prompt change.
9. **`gate()` and `apply_gate()` differ for underdetermined pairs below τ** (§12), and the Tier 1 runner uses `gate()`. Which semantics the A–D experiments report should be settled before bloat numbers are compared.
10. **Name variants have no merge semantics.** They are extracted and reported but neither gate nor lexicon treats them; the research plan wants same-entity name variants to merge, which needs a decision (e.g. a canonical-name key) before the secondary class can be evaluated.
11. **The Tier 1 v2 data and the six result runs are legacy-scope** (§14): 104 of 173 pairs target classes that are now out of scope, and 135 of the 933 stored rows do not validate against the current schema.
12. **Config A–D limitations.** (a) Config D, the bge-m3 loading path and the CLI have only run against fakes; judge behaviour on real outputs is known only for the 20-record A–C smoke test, and A, C and the judge have not been run on all 173 records. (b) Config B's native prompt is ours, not Mem0's; at 1.5B it is effectively English-forced (92% of facts translated), at 7B 41% of facts change script (Hinglish → Devanagari); corruption (hand-labelled) was 74% / 18% / 23% for 1.5B / 3B / 7B and the automatic corruption signals catch only a fraction of it. (c) The pair-level setting removes candidate retrieval, so L4 is isolated only as "cosine of these two texts vs tau", not top-k retrieval collisions. (d) The judge answers merge/keep_both only (no supersede). (e) A–C rows have `threshold: null`; the similarity score there is informational. (f) `diagnose` is lexicon-relative and sees nothing the lexicon does not cover; a pair counts as a storage loss only when the stored texts collapsed. (g) Gate-off runs use the strategy labels `mem0` / `store-surface-only` / `embedding-threshold` for this repo's own pipeline, not the real packages. (h) The 7B model is sharded over two GPUs, whose numerics may differ slightly from single-GPU runs.
13. **Tier 2 limitations** (user-only over-merging by the Config C judge, transitive contamination, judge backbone ≠ Tier 1, German du/Sie, mirror-arm confounds) are listed in §13d.

---

## 18. File-to-concept map

| File | Concept(s) it owns |
|---|---|
| `dkmem/memory/schema.py` | `ProbeItem`, `Extraction`, `MergeEvent`, JSONL I/O |
| `dkmem/memory/scope.py` | The in-scope / cannot-link / out-of-scope / legacy distinction-class sets (single source of truth) |
| `dkmem/config.py` | Names for configurations A–D, DK-Mem modes, strategy list (no behaviour) |
| `dkmem/memory/prompts.py` | Frozen extraction prompt text (v1/v2/v3 legacy, v4 final + `DEFAULT_EXTRACTION_PROMPT`) |
| `dkmem/backends/llm.py` | `HFGenerator`, `ModelConfig`, `GenerationParams` (Qwen backend) |
| `dkmem/memory/extract.py` | Baseline extraction, output validation, `derive_lang_profile` |
| `dkmem/memory/lexicon.py` | `Lexicon`, `LexiconEntry`, `load_lexicon` |
| `dkmem/memory/distinction_features.json` | The actual 15-entry lexicon data |
| `dkmem/memory/matcher.py` | Tokenizing + scanning text against the lexicon |
| `dkmem/memory/dkmem_extract.py` | Lexicon-first/model-second merge (the real "DK-Mem extractor") |
| `dkmem/memory/cache.py` | `ExtractionCache` (verified, append-only, keyed by config) |
| `dkmem/memory/similarity.py` | `gloss_similarity`, `SimilarityMetric`, `entry_similarity`, `candidate_pairs` (no gate import) |
| `dkmem/memory/consolidation.py` | `evaluate_pair` — the only place similarity and the gate are connected |
| `dkmem/memory/gate.py` | `compatible`, `gate`, `apply_gate`/`GateResult` (veto layer), `build_merge_event` |
| `dkmem/tier1/extraction.py` | `extract_lexicon_only` (no-LLM strategy) |
| `dkmem/tier1/io.py` | Input loading/validation, output schema translation, manifest/eval writers |
| `dkmem/tier1/runner.py` | `run_episode_lexicon_only` / `run_episode_lexicon_llm`, wiring everything together per episode |
| `dkmem/memory/judge.py` | `MERGE_JUDGE_V1`, strict judge parser, `judge_pairs` (the LLM host for Configs A–C) |
| `dkmem/memory/native_extract.py` | `NATIVE_B_V1` (the frozen Config B prompt), fact parser, `extraction_checks`, `output_language_report` (classifier v2); legacy `MEM0_DEFAULT_FACTS_V1` |
| `dkmem/backends/embedding.py` | `BgeM3Embedder`, `cosine_metric` (Config D) |
| `dkmem/pipeline/runner.py` | `run_stage_attribution`, `build_run_config`, `write_outputs`, `strategy_for` |
| `dkmem/pipeline/trace.py` | Hashes, git state, source-file hashes, loss-point `diagnose` / `diagnose_dropped` |
| `dkmem/pipeline/cli.py` | `python -m dkmem.pipeline.cli` |
| `dkmem/baselines/mem0/{source,memory,events,runner}.py` | Pinned Mem0 v1.0.11 sources and loader; the `Memory.add` flow; event → pair-decision mapping; the Tier 1 runner and outputs |
| `dkmem/baselines/mem0/upstream/*.py.txt` | The vendored upstream files (data, hash-pinned, never imported) |
| `dkmem/baselines/flat.py` | `NeverMergeHost`, the flat-RAG Tier 1 runner, Tier 2 ingestion / retrieval / QA |
| `dkmem/baselines/cli.py` | `python -m dkmem.baselines.cli mem0 | flat` |
| `dkmem/eval/{gold,metrics,groups}.py` | The gold key, FCR/MCR per the contract, loading run groups |
| `dkmem/eval/{sweep,ablation,fairness,cli}.py` | Raise-τ sweep and frontier, DK-Mem ablation, fairness check, the evaluation CLI |
| `tier1_results/*/` | The six actual completed runs (legacy scope, not regenerated) |
| `eval/tier2/{run_tier2,memory_store,contract}.py` | Tier 2 runner (separate judge / QA models), persistent store, contract validation and injected-pair mapping |
| `eval/tier2/{judge_entity,judge_host,frozen_judge,judge_provenance}.py` | Tier 2 Config C identity judges (v1 failed; v2 frozen), allow-listed judge host, pinned prompt hashes, provenance labels |
| `eval/tier2/judge_validation{,_v2,_7b}/` | Frozen judge-validation sets, criteria, scorers, freeze records; `run_cases.py`, `memory_probe.py` |
| `eval/tier2/mirror_v1_1/` | Mirror (counter-confound) benchmark arm v1.1m: bank, generator, validator, frozen data |
| `validation/tier2_entity/build_kernels.py` | Kaggle notebooks for judge validation, the memory probe and Tier 2 runs (per arm, C+D or D only) |
| `eval/tier2_entity_runs/*/` | Downloaded validation, probe and smoke outputs (each with `MANIFEST.json`) |

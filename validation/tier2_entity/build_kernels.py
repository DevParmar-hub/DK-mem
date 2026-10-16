"""Build the Kaggle notebooks for the Tier-2 identity-judge work (Config C ``merge_judge_entity_t2_v1``).

Kinds (each writes ``<out>`` = only what ``kaggle kernels push -p <out>`` sees, and ``<out>.evaluator`` = never pushed):

  judge-validation   the frozen identity judge on the frozen validation pairs, both orders. The payload carries the pair TEXTS
                     only (``inputs/judge_cases.jsonl``: case_id, text_a, text_b); labels, criteria and the scorer stay local.
  tier2              the Tier-2 runner on one benchmark arm (``v1.0`` = the original frozen benchmark, ``mirror`` = the v1.1m
                     counter-confound arm), Config C with the identity judge and Config D, gate off/lexicon. Same payload rules as
                     the frozen-judge smoke kernel (validation/tier2_smoke/build_kernel.py, whose checks are reused): system-side
                     files only, uniform opaque passthrough, blinded question ids, projected FROZEN file.

    python build_kernels.py judge-validation --user U --slug S --out DIR
    python build_kernels.py tier2 --arm v1.0|mirror [--conversations ids|--smoke] --run-prefix P --user U --slug S --out DIR
    python build_kernels.py --check DIR          # freshness: the notebook still equals what the working tree builds

Nothing is pushed by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
NOTEBOOK_NAME = "dkmem_tier2_entity.ipynb"
PUSHED_FILES = (NOTEBOOK_NAME, "kernel-metadata.json")
MAX_NOTEBOOK_BYTES = 1_500_000

_spec = importlib.util.spec_from_file_location("_t2_smoke_build", os.path.join(REPO, "validation", "tier2_smoke", "build_kernel.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)
BuildError = S.BuildError

ENTITY_JUDGE_ID = "merge_judge_entity_t2_v2"     # the identity judge Tier-2 kernels use (v1 failed its validation)
JV_DIR = "eval/tier2/judge_validation"
JV_CASES = JV_DIR + "/cases_v1.jsonl"
# validation sets: labelled cases (evaluator side) and the judge they validate
JV_SETS = {"v1": {"cases": JV_CASES, "prompt": "merge_judge_entity_t2_v1"},
           "v2": {"cases": "eval/tier2/judge_validation_v2/cases_v2.jsonl", "prompt": "merge_judge_entity_t2_v2"},
           # the unchanged v2 prompt on Qwen2.5-7B (pinned revision of DKMEM_FIRST_RUN.md), sharded over 2 x T4
           "7b": {"cases": "eval/tier2/judge_validation_7b/cases_7b.jsonl", "prompt": "merge_judge_entity_t2_v2",
                  "model_id": "Qwen/Qwen2.5-7B-Instruct", "model_revision": "a09a35458c702b33eeacc393d103063234e8bc28", "shard": True},
           # kinship naming diagnostic of the frozen v2 judge (eval/tier2/kinship_probe/): same prompt, model, decoding
           "kin_probe": {"cases": "eval/tier2/kinship_probe/cases_v1.jsonl", "prompt": "merge_judge_entity_t2_v2",
                         "model_id": "Qwen/Qwen2.5-7B-Instruct", "model_revision": "a09a35458c702b33eeacc393d103063234e8bc28", "shard": True}}
JV_INPUT = "inputs/judge_cases.jsonl"
JV_SYSTEM_FILES = (
    "eval/tier2/__init__.py", "eval/tier2/judge_entity.py", "eval/tier2/judge_host.py", "eval/tier2/frozen_judge.py",
    JV_DIR + "/__init__.py", JV_DIR + "/run_cases.py", "eval/harness/__init__.py", "eval/harness/_dkmem.py",
)
# evaluator-side judge-validation material: refused anywhere in a payload path or in the inputs
JV_FORBIDDEN_NAME_PARTS = ("cases_v1", "criteria_v1", "cases_v2", "criteria_v2", "judge_validation_v2", "cases_7b", "criteria_7b",
                           "judge_validation_7b", "kinship_probe", "review_sheet", "review_log", "freeze", "score.py", "score_v2",
                           "score_7b", "make_cases")
JV_LABEL_FIELDS = ("expected", "category", "role", "attribute_pattern", "contested", "note")

ARMS = {
    "v1.0": {"root": "eval/tier2", "frozen": "eval/tier2/FROZEN_v1.0.json", "data": "eval/tier2/data"},
    "mirror": {"root": "eval/tier2/mirror_v1_1", "frozen": "eval/tier2/mirror_v1_1/FROZEN_v1.1m.json", "data": "eval/tier2/mirror_v1_1/data"},
}
TIER2_SYSTEM_FILES = S.SYSTEM_FILES      # includes eval/tier2/judge_entity.py
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
MODEL_ID, MODEL_REVISION = "Qwen/Qwen2.5-3B-Instruct", "aa8e72537993ba99e69dfaafa59ed015b17504d1"
# Config C judge on Tier 2: the validated frozen v2 prompt on the pinned Qwen2.5-7B (eval/tier2_entity_runs/judge_v2_7b_validation_20261014),
# sharded so that it fits beside the 3B QA answerer and bge-m3 on 2 x T4 (caps verified by the memory-probe kernel). The QA answerer stays the
# pinned 3B for every config, so QA is comparable between C and D. NOTE: the judge backbone differs from Tier 1's (3B).
JUDGE_MODEL_ID, JUDGE_MODEL_REVISION = "Qwen/Qwen2.5-7B-Instruct", "a09a35458c702b33eeacc393d103063234e8bc28"
JUDGE_MAX_MEMORY = "0=5GiB,1=11GiB"
JUDGE_ARGS = ["--judge-model-id", JUDGE_MODEL_ID, "--judge-model-revision", JUDGE_MODEL_REVISION, "--judge-shard", "--judge-max-memory", JUDGE_MAX_MEMORY]
SIMILARITY_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


def _read(rel: str) -> str:
    return S._read_lf(os.path.join(REPO, rel))


def _dkmem_files() -> dict[str, str]:
    files = {}
    for dirpath, dirnames, filenames in os.walk(os.path.join(REPO, "dkmem")):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for fn in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, fn), REPO).replace(os.sep, "/")
            if fn.endswith(S.DKMEM_SUFFIXES) and not rel.startswith(S.DKMEM_EXCLUDED_PREFIXES):
                files[rel] = _read(rel)
    return files


# --- judge validation ---------------------------------------------------------------------------------------------


def jv_inputs(jv_set: str = "v1") -> str:
    rows = [json.loads(l) for l in _read(JV_SETS[jv_set]["cases"]).splitlines() if l.strip()]
    return "".join(json.dumps({"case_id": r["case_id"], "text_a": r["text_a"], "text_b": r["text_b"]}, ensure_ascii=False) + "\n" for r in rows)


def jv_collect(jv_set: str = "v1") -> dict[str, str]:
    files = _dkmem_files()
    for rel in JV_SYSTEM_FILES:
        files[rel] = _read(rel)
    files[JV_INPUT] = jv_inputs(jv_set)
    return files


def jv_check(files: dict[str, str], jv_set: str = "v1") -> None:
    allowed = set(JV_SYSTEM_FILES) | {JV_INPUT}
    for n, t in files.items():
        low = n.lower()
        if not n.startswith("dkmem/") and n not in allowed:
            raise BuildError(f"not part of the judge-validation payload: {n}")
        hit = [p for p in (*S.FORBIDDEN_NAME_PARTS, *JV_FORBIDDEN_NAME_PARTS) if p in low]
        if hit:
            raise BuildError(f"evaluator-only material would be embedded ({hit}): {n}")
        if n.startswith(S.DKMEM_EXCLUDED_PREFIXES):
            raise BuildError(f"excluded dkmem tree would be embedded: {n}")
        if "\r" in t:
            raise BuildError(f"carriage returns would change the file's hash on Kaggle: {n}")
    for r in (json.loads(l) for l in files[JV_INPUT].splitlines() if l.strip()):
        if set(r) != {"case_id", "text_a", "text_b"}:
            raise BuildError(f"judge input rows must carry no labels: {sorted(r)}")
    leaked = [f for f in JV_LABEL_FIELDS if f'"{f}"' in files[JV_INPUT]]
    if leaked:
        raise BuildError(f"label fields in the judge input: {leaked}")
    cases_sha = hashlib.sha256(_read(JV_SETS[jv_set]["cases"]).encode("utf-8")).hexdigest()
    if any(cases_sha == hashlib.sha256(t.encode("utf-8")).hexdigest() for t in files.values()):
        raise BuildError("the labelled cases file would be embedded")


def jv_run_args(jv_set: str = "v1") -> list[str]:
    s = JV_SETS[jv_set]
    args = ["--cases", "/kaggle/working/src/" + JV_INPUT, "--out", "/kaggle/working/judge_validation",
            "--seed", "0", "--model-id", s.get("model_id", MODEL_ID), "--model-revision", s.get("model_revision", MODEL_REVISION)]
    if jv_set == "v1":
        return args                                   # v1 used the runner's default prompt
    return args + ["--prompt", s["prompt"]] + (["--shard"] if s.get("shard") else [])


_JV_SUMMARY = '''
import hashlib, json
rows = [json.loads(l) for l in open("/kaggle/working/judge_validation/judge_outputs.jsonl", encoding="utf-8") if l.strip()]
from collections import Counter
def dec(raw):
    try:
        d = json.loads(raw)
        return d.get("decision") if isinstance(d, dict) and set(d) == {"decision", "reason"} else None
    except ValueError:
        return None
summary = {"calls": len(rows), "decisions": dict(Counter(str(dec(r["raw_output"])) for r in rows)),
           "prompt": sorted({(r["prompt_id"], r["prompt_sha256"]) for r in rows}),
           "output_tokens_max": max(r["output_tokens"] for r in rows), "at_budget": sum(r["output_tokens"] >= r["max_new_tokens"] for r in rows),
           "payload_tree_sha256": TREE_SHA256, "gpu": GPU_LIST, "args": ARGS,
           "inputs_sha256": hashlib.sha256(open("/kaggle/working/src/@@INPUT@@", "rb").read()).hexdigest()}
json.dump(summary, open("/kaggle/working/judge_validation_summary.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
'''


def _run_cell(module: str, args: list[str], extra: str = "") -> str:
    return f"""
ARGS = {json.dumps(args)}
TREE_SHA256 = "@@TREE@@"
{extra}
print("python -m {module}", " ".join(ARGS), flush=True)
t0 = time.time()
proc = subprocess.Popen([sys.executable, "-m", "{module}", *ARGS], cwd=os.path.join(SRC, "eval"), stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, env={{**os.environ, "PYTHONPATH": os.path.join(SRC, "eval") + os.pathsep + SRC}})
for line in proc.stdout:
    print(line, end="", flush=True)
rc = proc.wait()
print("exit code", rc, "| seconds", round(time.time() - t0, 1))
assert rc == 0
"""


def _scan_cell(forbidden: tuple[str, ...], import_module: str) -> str:
    return S._FORBIDDEN_SCAN_CELL.replace("@@FORBIDDEN@@", json.dumps(list(forbidden))).replace("tier2.run_tier2", import_module)


def _notebook(title: str, files: dict[str, str], cells_after_scan: list[dict], forbidden, import_module: str) -> tuple[dict, str, str]:
    payload = S.make_payload(files)
    manifest = S.manifest_of(files)
    tree = S.tree_sha256(manifest)
    unpack = (S._UNPACK_CELL.replace("@@PAYLOAD@@", payload).replace("@@PAYLOAD_SHA256@@", hashlib.sha256(payload.encode("ascii")).hexdigest())
              .replace("@@MANIFEST@@", json.dumps(json.dumps(manifest, sort_keys=True))))
    cells = [S._md(title), S._code(unpack), S._code(_scan_cell(forbidden, import_module))]
    for c in cells_after_scan:
        c = dict(c)
        c["source"] = [s.replace("@@TREE@@", tree) for s in c["source"]]
        cells.append(c)
    nb = {"cells": cells, "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    S.verify_payload(payload, files)
    return nb, payload, tree


def build_judge_validation(jv_set: str = "v1"):
    files = jv_collect(jv_set)
    jv_check(files, jv_set)
    args = jv_run_args(jv_set)
    cells = [S._code(_run_cell("tier2.judge_validation.run_cases", args)), S._code(_JV_SUMMARY.replace("@@INPUT@@", JV_INPUT))]
    title = ("# DK-Mem Tier 2: frozen identity judge (merge_judge_entity_t2_v1) on the frozen validation pairs, both orders" if jv_set == "v1" else
             f"# DK-Mem Tier 2: frozen identity judge ({JV_SETS[jv_set]['prompt']}) on the frozen {jv_set} validation pairs, both orders"
             + (f" -- judge backbone {JV_SETS[jv_set]['model_id']} (NOT the Tier-1 backbone)" if "model_id" in JV_SETS[jv_set] else ""))
    nb, payload, tree = _notebook(title,
                                  files, cells, (*S.FORBIDDEN_NAME_PARTS, *JV_FORBIDDEN_NAME_PARTS), "tier2.judge_validation.run_cases")
    ev = {"kind": "judge-validation", "run_args": args, "inputs_sha256": hashlib.sha256(files[JV_INPUT].encode("utf-8")).hexdigest(),
          "cases_sha256": hashlib.sha256(_read(JV_SETS[jv_set]["cases"]).encode("utf-8")).hexdigest(), "set": jv_set}
    return files, nb, payload, tree, ev, {}


# --- Tier-2 runs (one arm) ----------------------------------------------------------------------------------------


def arm_paths(arm: str) -> dict:
    a = ARMS[arm]
    return {**a, "conversations": a["data"] + "/tier2_conversations.jsonl", "questions": a["data"] + "/tier2_qa_questions.jsonl"}


def t2_collect(arm: str) -> tuple[dict[str, str], dict[str, str]]:
    """``(payload files, qa id map)`` for one arm. The arm's data sits at the arm's own path; its FROZEN file is projected."""
    p = arm_paths(arm)
    files = _dkmem_files()
    for rel in TIER2_SYSTEM_FILES:
        if rel != S.FROZEN_FILE:
            files[rel] = _read(rel)
    frozen_text = _read(p["frozen"])
    pins = json.loads(frozen_text)["sha256"]
    conv, qs = _read(p["conversations"]), _read(p["questions"])
    for rel, text in (("data/tier2_conversations.jsonl", conv), ("data/tier2_qa_questions.jsonl", qs)):
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != pins[rel]:
            raise BuildError(f"{arm}: {rel} no longer matches its frozen pin")
    view, qmap = S.blind_questions(qs)
    files[p["conversations"]] = conv
    files[p["questions"]] = view
    files[p["frozen"]] = S.project_frozen(frozen_text, questions_view_sha256=hashlib.sha256(view.encode("utf-8")).hexdigest())
    files[S.PASSTHROUGH] = S.make_passthrough(conv)
    return files, qmap


def t2_check(files: dict[str, str], arm: str) -> None:
    """The frozen-judge smoke builder's checks, pointed at this arm's paths."""
    p = arm_paths(arm)
    saved = (S.FROZEN_FILE, S.CONVERSATIONS, S.QUESTIONS, S.DATA_FILES, S.ALLOWED_NON_DKMEM, S.REQUIRED_FILES)
    try:
        S.FROZEN_FILE, S.CONVERSATIONS, S.QUESTIONS = p["frozen"], p["conversations"], p["questions"]
        S.DATA_FILES = (p["conversations"], p["questions"])
        S.ALLOWED_NON_DKMEM = (set(TIER2_SYSTEM_FILES) - {"eval/tier2/FROZEN_v1.0.json"}) | {p["frozen"], *S.DATA_FILES, S.PASSTHROUGH}
        S.REQUIRED_FILES = ("dkmem/memory/judge.py", "dkmem/pairwise_eval.schema.json", "dkmem/run_manifest.schema.json", *S.ALLOWED_NON_DKMEM)
        _orig = S._check_inputs

        def _arm_inputs(fs):
            # the data files are pinned under data/ relative to the arm root
            fz = json.loads(fs[p["frozen"]])["sha256"]
            for rel in S.DATA_FILES:
                if hashlib.sha256(fs[rel].encode("utf-8")).hexdigest() != fz[rel.removeprefix(p["root"] + "/")]:
                    raise BuildError(f"{rel} does not match its pin")
            # the shared check looks pins up by the path below eval/tier2/; give it that alias (a copy, the payload is unchanged)
            proj = json.loads(fs[p["frozen"]])
            proj["sha256"] = {**proj["sha256"], **{rel.removeprefix("eval/tier2/"): proj["sha256"][rel.removeprefix(p["root"] + "/")]
                                                  for rel in S.DATA_FILES}}
            return _orig({**fs, p["frozen"]: json.dumps(proj)})
        S._check_inputs = _arm_inputs
        # an EMPTY pinned file (the mirror arm's QA files) carries nothing; its hash equals every empty __init__.py
        _orig_protected = S.protected_hashes
        S.protected_hashes = lambda fs: _orig_protected(fs) - {EMPTY_SHA256}
        # the generic check strips "eval/tier2/" to find a pin; give it the arm-relative key too
        S.check_payload(files)
    finally:
        S._check_inputs = _orig if "_orig" in locals() else S._check_inputs
        S.protected_hashes = _orig_protected if "_orig_protected" in locals() else S.protected_hashes
        S.FROZEN_FILE, S.CONVERSATIONS, S.QUESTIONS, S.DATA_FILES, S.ALLOWED_NON_DKMEM, S.REQUIRED_FILES = saved
    if '"' + ENTITY_JUDGE_ID + '"' not in files["eval/tier2/judge_entity.py"]:
        raise BuildError("the identity judge is missing from the payload")


def smoke_conversations(files: dict[str, str], arm: str) -> list[str]:
    """Label-free, deterministic: the first two Hindi conversations and the first German one, in file order."""
    p = arm_paths(arm)
    saved = S.CONVERSATIONS
    try:
        S.CONVERSATIONS = p["conversations"]
        return S.select_conversations(files)
    finally:
        S.CONVERSATIONS = saved


ALL_CONFIGS = "C:off,C:lexicon,D:off,D:lexicon"
D_CONFIGS = "D:off,D:lexicon"


def t2_run_args(arm: str, conversations: list[str] | None, run_prefix: str, tau: float = 0.90, seed: int = 0,
                configs: str = ALL_CONFIGS) -> list[str]:
    p = arm_paths(arm)
    args = ["--progress", "--passthrough", "/kaggle/working/src/" + S.PASSTHROUGH, "--data-dir", "/kaggle/working/src/" + p["data"],
            "--frozen", "/kaggle/working/src/" + p["frozen"]]
    if "C:" in configs:
        args += ["--judge-prompt", ENTITY_JUDGE_ID, *JUDGE_ARGS]
    if conversations:
        args += ["--conversations", ",".join(conversations)]
    return args + ["--configs", configs, "--tau", str(tau), "--seed", str(seed), "--run-prefix", run_prefix,
                   "--out", "/kaggle/working/runs", "--model-id", MODEL_ID, "--model-revision", MODEL_REVISION,
                   "--similarity-revision", SIMILARITY_REVISION]


def _t2_summary_cell(n_conversations: int, has_questions: bool, d_only: bool = False) -> str:
    cell = S._SUMMARY_CELL.replace("@@OUTDIR@@", "/kaggle/working").replace("@@PTPATH@@", "/kaggle/working/src/" + S.PASSTHROUGH)
    cell = cell.replace('FROZEN = "3855ef65f50e9a0f017710e5c0d0cb5a63d210a7547fa0e0e336d4c77a45c5ff"',
                        'FROZEN = "' + _entity_sha() + '"')
    cell = cell.replace('e["judge"]["prompt_id"] == "merge_judge_v1"', 'e["judge"]["prompt_id"] == "' + ENTITY_JUDGE_ID + '"')
    if not has_questions:      # an arm without QA (mirror): there is nothing to blind or answer
        cell = cell.replace('"qa_ids_opaque": bool(runs) and all(e["qa"]["ids_opaque"] and e["qa"]["answers"] > 0 for e in runs),',
                            '"qa_ids_opaque": bool(runs) and all(e["qa"]["answers"] == 0 for e in runs),')
        cell = cell.replace('"questions_read_after_consolidation": bool(runs) and all(e["info"].get("questions_loaded_lazily") for e in runs),',
                            '"questions_read_after_consolidation": True,')
    if not d_only:             # the judge is the pinned 7B, loaded separately; QA is the pinned 3B in every run
        cell = cell.replace("accept = {", _JUDGE_MODEL_CHECK + "accept = {\n" + _JUDGE_MODEL_ACCEPT, 1)
    if d_only:                 # Config D only: no judge; the D rule's threshold is the run-level tau in every row
        start, end = cell.index("accept = {"), cell.index('summary["acceptance"] = accept')
        cell = cell[:start] + _D_ONLY_ACCEPT + cell[end:]
    cell = cell.replace("smoke acceptance failed", "acceptance failed")
    return (cell.replace("@@JM@@", JUDGE_MODEL_ID).replace("@@JR@@", JUDGE_MODEL_REVISION)
            .replace("@@QM@@", MODEL_ID).replace("@@QR@@", MODEL_REVISION))


_JUDGE_MODEL_CHECK = '''models = {}
for rid in summary["runs"]:
    m = json.load(open(OUTDIR + "/runs/" + rid + "/run_manifest.json", encoding="utf-8"))
    models[rid] = {"config": m["pipeline_config"], "judge_backbone": m.get("judge_backbone"), "judge_separate": m.get("judge_model_separate_from_qa"),
                   "judge_revision": (m.get("generation_run_info") or {}).get("resolved_revision"),
                   "qa_backbone": m["tier2"]["qa"]["generation_run_info"].get("backbone"), "qa_revision": m["tier2"]["qa"]["generation_run_info"].get("resolved_revision")}
summary["models"] = models
'''
_JUDGE_MODEL_ACCEPT = ('    "judge_is_the_pinned_7b_and_separate": bool(c_runs) and all(v["judge_backbone"] == "@@JM@@" and v["judge_revision"] == "@@JR@@" '
                       'and v["judge_separate"] is True for v in models.values() if v["config"] == "C"),\n'
                       '    "qa_is_the_pinned_3b_in_every_run": bool(runs) and all(v["qa_backbone"] == "@@QM@@" and v["qa_revision"] == "@@QR@@" '
                       'for v in models.values()),\n')
_D_ONLY_ACCEPT = '''d_runs = [e for e in runs if e["pipeline_config"] == "D"]
TAU = float(ARGS[ARGS.index("--tau") + 1])
accept = {
    "two_d_runs_only": len(runs) == 2 and len(d_runs) == 2 and sorted(e["dkmem_mode"] for e in runs) == ["lexicon", "off"],
    "no_judge_log": all("judge" not in e for e in runs),
    "d_threshold_is_tau": all(e["thresholds"] == [repr(TAU)] for e in runs),
    "tier2_manifests": bool(runs) and all(e["dataset_tier"] == "tier2_injected_sessions" for e in runs),
    "evaluator_files_absent": bool(runs) and all(len(e["frozen_files_not_in_payload"]) > 0 for e in runs),
    "passthrough_is_the_payload_file": bool(runs) and all(e["passthrough_sha256"] == PT_SHA for e in runs),
    "qa_ids_opaque": @@QA_OPAQUE@@,
    "questions_read_after_consolidation": @@QA_LAZY@@,
}
'''


def _entity_sha(judge: str = ENTITY_JUDGE_ID) -> str:
    const = {"merge_judge_entity_t2_v1": "ENTITY_JUDGE_PROMPT_SHA256", "merge_judge_entity_t2_v2": "ENTITY_JUDGE_V2_PROMPT_SHA256"}[judge]
    m = re.search(const + r' = "([0-9a-f]{64})"', _read("eval/tier2/frozen_judge.py"))
    return m.group(1)


def build_tier2(arm: str, conversations: list[str] | None, smoke: bool, run_prefix: str, configs: str = ALL_CONFIGS):
    if configs not in (ALL_CONFIGS, D_CONFIGS):
        raise BuildError(f"configs must be {ALL_CONFIGS!r} or {D_CONFIGS!r}")
    d_only = configs == D_CONFIGS
    files, qmap = t2_collect(arm)
    t2_check(files, arm)
    p = arm_paths(arm)
    known = [c["conversation_id"] for c in S._jsonl(files[p["conversations"]])]
    if smoke:
        conversations = smoke_conversations(files, arm)
    if conversations and not set(conversations) <= set(known):
        raise BuildError(f"unknown conversation ids: {sorted(set(conversations) - set(known))}")
    args = t2_run_args(arm, conversations, run_prefix, configs=configs)
    has_q = bool(files[p["questions"]].strip())
    summary = _t2_summary_cell(len(conversations or known), has_q, d_only)
    if d_only:
        summary = (summary.replace("@@QA_OPAQUE@@", 'bool(runs) and all(e["qa"]["ids_opaque"] and e["qa"]["answers"] > 0 for e in runs)' if has_q
                                   else 'bool(runs) and all(e["qa"]["answers"] == 0 for e in runs)')
                   .replace("@@QA_LAZY@@", 'bool(runs) and all(e["info"].get("questions_loaded_lazily") for e in runs)' if has_q else "True"))
    cells = [S._code(_run_cell("tier2.run_tier2", args, f"CONVERSATIONS = {json.dumps(conversations or known)}")), S._code(summary)]
    title = (f"# DK-Mem Tier 2 ({arm} arm): Config D only (embedding threshold, gate off/lexicon), {len(conversations or known)} conversations"
             if d_only else
             f"# DK-Mem Tier 2 ({arm} arm): Config C identity judge {ENTITY_JUDGE_ID} on {JUDGE_MODEL_ID} (judge backbone differs from Tier 1) "
             f"+ Config D; QA answerer {MODEL_ID} for every config; {len(conversations or known)} conversations")
    nb, payload, tree = _notebook(title, files, cells, S.FORBIDDEN_NAME_PARTS, "tier2.run_tier2")
    ev = {"kind": "tier2", "arm": arm, "smoke": smoke, "configs": configs, "run_args": args, "conversations": conversations or known,
          "passthrough_sha256": hashlib.sha256(files[S.PASSTHROUGH].encode("utf-8")).hexdigest(),
          "qa_questions_view_sha256": hashlib.sha256(files[p["questions"]].encode("utf-8")).hexdigest()}
    return files, nb, payload, tree, ev, qmap


# --- writing / checking -------------------------------------------------------------------------------------------


PROBE_FILES = (*[f for f in TIER2_SYSTEM_FILES if f != S.FROZEN_FILE], JV_DIR + "/__init__.py", JV_DIR + "/run_cases.py", JV_DIR + "/memory_probe.py")


def build_memory_probe():
    """Both models resident at once (3B QA + sharded 7B judge + bge-m3), loaded by the runner's own builders; the 7B validation pair
    TEXTS are judged again in the same order and batching so the outputs can be compared with the validated run. No benchmark data."""
    files = _dkmem_files()
    for rel in PROBE_FILES:
        files[rel] = _read(rel)
    files[JV_INPUT] = jv_inputs("7b")
    allowed = set(PROBE_FILES) | {JV_INPUT}
    for n, text in files.items():
        if not n.startswith("dkmem/") and n not in allowed:
            raise BuildError(f"not part of the memory-probe payload: {n}")
        if any(x in n.lower() for x in (*S.FORBIDDEN_NAME_PARTS, *JV_FORBIDDEN_NAME_PARTS)) or n.startswith(S.DKMEM_EXCLUDED_PREFIXES):
            raise BuildError(f"evaluator-only material would be embedded: {n}")
        if "\r" in text:
            raise BuildError(f"carriage returns: {n}")
    if any(n.startswith("eval/tier2/data") or "mirror_v1_1" in n for n in files):
        raise BuildError("the memory probe carries no benchmark data")
    jv_check({k: v for k, v in files.items() if k.startswith("dkmem/") or k in set(JV_SYSTEM_FILES) | {JV_INPUT}}, "7b")
    args = ["--cases", "/kaggle/working/src/" + JV_INPUT, "--out", "/kaggle/working/memory_probe", "--judge-prompt", ENTITY_JUDGE_ID,
            "--model-id", MODEL_ID, "--model-revision", MODEL_REVISION, "--similarity-revision", SIMILARITY_REVISION, *JUDGE_ARGS]
    cells = [S._code(_run_cell("tier2.judge_validation.memory_probe", args))]
    nb, payload, tree = _notebook("# DK-Mem Tier 2: GPU-memory probe -- Qwen2.5-3B QA + sharded Qwen2.5-7B judge + bge-m3 on 2 x T4",
                                  files, cells, (*S.FORBIDDEN_NAME_PARTS, *JV_FORBIDDEN_NAME_PARTS), "tier2.judge_validation.memory_probe")
    ev = {"kind": "memory-probe", "run_args": args, "inputs_sha256": hashlib.sha256(files[JV_INPUT].encode("utf-8")).hexdigest()}
    return files, nb, payload, tree, ev, {}


BATCH_DIAG_SOURCE = "eval/tier2_entity_runs/cd7b_smoke_v10_20261014/runs/t2cd7b-smoke-v10-store-surface-only-C_seed0.judge_log.jsonl"
BATCH_DIAG_INPUT = "inputs/judge_calls.jsonl"


def batch_diag_calls() -> str:
    """The 135 judge calls of the v1.0 combined smoke (C/off), in the runner's order: texts plus sequential call and group indices only
    (no turn ids, no labels, no injected/distractor marks). The group is the runner's judge call (one per later entry)."""
    rows = [json.loads(l) for l in _read(BATCH_DIAG_SOURCE).splitlines() if l.strip()]
    group_of, out = {}, []
    for i, r in enumerate(rows):
        g = group_of.setdefault((r["conversation_id"], r["turn_id_b"]), len(group_of))
        out.append(json.dumps({"call_id": f"c{i:03d}", "group": f"g{g:03d}", "text_a": r["text_a"], "text_b": r["text_b"]}, ensure_ascii=False))
    return "".join(x + "\n" for x in out)


def build_batch_diagnostic():
    files = _dkmem_files()
    for rel in (*PROBE_FILES, JV_DIR + "/batch_diagnostic.py"):
        files[rel] = _read(rel)
    files[BATCH_DIAG_INPUT] = batch_diag_calls()
    allowed = set(PROBE_FILES) | {JV_DIR + "/batch_diagnostic.py", BATCH_DIAG_INPUT}
    for n, text in files.items():
        if not n.startswith("dkmem/") and n not in allowed:
            raise BuildError(f"not part of the batch-diagnostic payload: {n}")
        if any(x in n.lower() for x in (*S.FORBIDDEN_NAME_PARTS, *JV_FORBIDDEN_NAME_PARTS)) or n.startswith(S.DKMEM_EXCLUDED_PREFIXES):
            raise BuildError(f"evaluator-only material would be embedded: {n}")
    for r in (json.loads(l) for l in files[BATCH_DIAG_INPUT].splitlines()):
        if set(r) != {"call_id", "group", "text_a", "text_b"} or re.search(r"t2[cm]_\d", r["call_id"] + r["group"]):
            raise BuildError("batch-diagnostic rows must carry texts and opaque indices only")
    args = ["--calls", "/kaggle/working/src/" + BATCH_DIAG_INPUT, "--out", "/kaggle/working/batch_diagnostic", "--judge-prompt", ENTITY_JUDGE_ID,
            "--judge-model-id", JUDGE_MODEL_ID, "--judge-model-revision", JUDGE_MODEL_REVISION, "--judge-shard", "--judge-max-memory", JUDGE_MAX_MEMORY]
    cells = [S._code(_run_cell("tier2.judge_validation.batch_diagnostic", args))]
    nb, payload, tree = _notebook("# DK-Mem Tier 2: batch-composition diagnostic of the frozen Config C judge (insitu vs batch 1 vs batch 8)",
                                  files, cells, (*S.FORBIDDEN_NAME_PARTS, *JV_FORBIDDEN_NAME_PARTS), "tier2.judge_validation.batch_diagnostic")
    ev = {"kind": "batch-diagnostic", "run_args": args, "source": BATCH_DIAG_SOURCE,
          "inputs_sha256": hashlib.sha256(files[BATCH_DIAG_INPUT].encode("utf-8")).hexdigest()}
    return files, nb, payload, tree, ev, {}


def _build(spec: dict):
    if spec["kind"] == "batch-diagnostic":
        return build_batch_diagnostic()
    if spec["kind"] == "memory-probe":
        return build_memory_probe()
    if spec["kind"] == "judge-validation":
        return build_judge_validation(spec.get("set", "v1"))
    return build_tier2(spec["arm"], spec.get("conversations_arg"), spec.get("smoke", False), spec["run_prefix"], spec.get("configs", ALL_CONFIGS))


def write(spec: dict, user: str, slug: str, out: str) -> int:
    ev_dir = S.evaluator_dir(out)
    try:
        for d in (out, ev_dir):
            if os.path.exists(d) and os.listdir(d):
                raise BuildError(f"{d} exists and is not empty; use a new directory")
        files, nb, payload, tree, ev, qmap = _build(spec)
        text = json.dumps(nb, indent=1, ensure_ascii=False)
        if len(text.encode("utf-8")) > MAX_NOTEBOOK_BYTES:
            raise BuildError(f"the notebook is {len(text.encode('utf-8')):,} bytes")
    except BuildError as e:
        print(f"build_kernels: refusing to write the notebook: {e}", file=sys.stderr)
        return 1
    os.makedirs(out, exist_ok=True)
    os.makedirs(ev_dir, exist_ok=True)
    with open(os.path.join(out, NOTEBOOK_NAME), "w", encoding="utf-8") as f:
        f.write(text)
    meta = {"id": f"{user}/{slug}", "title": slug.replace("-", " ").title()[:60], "code_file": NOTEBOOK_NAME, "language": "python",
            "kernel_type": "notebook", "is_private": True, "enable_gpu": True, "enable_internet": True, "machine_shape": "NvidiaTeslaT4",
            "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}
    with open(os.path.join(out, "kernel-metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    listing = {"tree_sha256": tree, "n_files": len(files), "payload_sha256": hashlib.sha256(payload.encode("ascii")).hexdigest(),
               "files": [{"path": n, "sha256": hashlib.sha256(t.encode("utf-8")).hexdigest()} for n, t in sorted(files.items())]}
    with open(os.path.join(ev_dir, "payload_manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({**listing, **ev, "build_spec": spec}, f, indent=1)
    if spec["kind"] == "tier2":
        with open(os.path.join(ev_dir, "t2_passthrough_used.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            f.write(files[S.PASSTHROUGH])
        with open(os.path.join(ev_dir, S.QA_ID_MAP_FILE), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(qmap, indent=1, sort_keys=True))
    print("wrote", out, "(+", ev_dir, ") |", len(files), "files | tree sha256", tree[:16], "| notebook", f"{len(text.encode('utf-8')):,} B")
    return 0


def check(path: str) -> int:
    try:
        ev = json.load(open(os.path.join(S.evaluator_dir(path), "payload_manifest.json"), encoding="utf-8"))
        files, nb, payload, tree, _, qmap = _build(ev["build_spec"])
        have = json.load(open(os.path.join(path, NOTEBOOK_NAME), encoding="utf-8"))
        problems = []
        if sorted(os.listdir(path)) != sorted(PUSHED_FILES):
            problems.append(f"the pushed directory must hold exactly {list(PUSHED_FILES)}")
        if have != nb:
            problems.append("the notebook is not what the working tree builds")
        if ev["tree_sha256"] != tree:
            problems.append("payload tree hash differs")
        if ev["build_spec"]["kind"] == "tier2":
            used = open(os.path.join(S.evaluator_dir(path), "t2_passthrough_used.jsonl"), "rb").read()
            if used != files[S.PASSTHROUGH].encode("utf-8"):
                problems.append("t2_passthrough_used.jsonl is not the payload's passthrough")
            if json.load(open(os.path.join(S.evaluator_dir(path), S.QA_ID_MAP_FILE), encoding="utf-8")) != qmap:
                problems.append("qa_id_map.json differs")
    except (OSError, ValueError, KeyError, BuildError) as e:
        print(f"build_kernels --check: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if problems:
        print("build_kernels --check: STALE: " + "; ".join(problems), file=sys.stderr)
        return 1
    print(f"build_kernels --check: fresh | {len(files)} files | tree sha256 {tree[:16]}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", metavar="KERNEL_DIR")
    ap.add_argument("kind", nargs="?", choices=("judge-validation", "tier2", "memory-probe", "batch-diagnostic"))
    ap.add_argument("--arm", choices=tuple(ARMS))
    ap.add_argument("--set", choices=tuple(JV_SETS), default="v1", help="judge-validation set (v2 validates merge_judge_entity_t2_v2)")
    ap.add_argument("--conversations")
    ap.add_argument("--smoke", action="store_true", help="first two Hindi + first German conversation of the arm (label-free)")
    ap.add_argument("--run-prefix")
    ap.add_argument("--configs", choices=("all", "D"), default="all", help="tier2: C+D (default) or Config D only")
    ap.add_argument("--user")
    ap.add_argument("--slug")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.check:
        return check(a.check)
    if not (a.kind and a.user and a.slug and a.out):
        ap.error("kind, --user, --slug and --out are required (or --check DIR)")
    spec = {"kind": a.kind}
    if a.kind == "judge-validation" and a.set != "v1":
        spec["set"] = a.set
    if a.kind == "tier2":
        if not (a.arm and a.run_prefix):
            ap.error("tier2 needs --arm and --run-prefix")
        spec.update(arm=a.arm, run_prefix=a.run_prefix, smoke=a.smoke, conversations_arg=a.conversations.split(",") if a.conversations else None)
        if a.configs == "D":
            spec["configs"] = D_CONFIGS
    return write(spec, a.user, a.slug, a.out)


if __name__ == "__main__":
    sys.exit(main())

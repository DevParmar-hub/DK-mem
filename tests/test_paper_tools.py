"""The paper pipeline's own tooling: numbers reproduce the verified report, review summaries count every verdict, the paper checker catches
what "done" forbids. Stored-report cases skip when the (gitignored) report is absent, i.e. for teammates without the artifacts."""

import csv
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parent.parent


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NUM = load("paper/tools/make_numbers.py", "make_numbers")
REV = load("paper/tools/summarize_reviews.py", "summarize_reviews")
CHK = load("tools/check_paper.py", "check_paper")


class TestWilson(unittest.TestCase):
    def test_known_values(self):
        lo, hi = NUM.wilson(15, 42)
        self.assertAlmostEqual(lo, 0.2299, places=3)
        self.assertAlmostEqual(hi, 0.5083, places=3)          # the stored report's interval for 15/42 is [0.2299, 0.5083]
        self.assertEqual(NUM.wilson(0, 27)[0], 0.0)


@unittest.skipUnless(NUM.REPORT.exists(), "verified entity report not present (held by the lead)")
class TestNumbersFromTheStoredReport(unittest.TestCase):
    def setUp(self):
        self.nums = NUM.build(json.loads(NUM.REPORT.read_bytes()), set())

    def test_hindi_and_german_partition_the_pairs_exactly(self):
        for arm in self.nums["arms"].values():
            for e in arm["runs"].values():
                self.assertEqual(e["by_language_n"], {"de": 6, "hi": 63})
                self.assertEqual(e["hindi"]["FCR"]["n"] + 6, e["all"]["FCR"]["n"])
                self.assertEqual(e["hindi"]["MCR"]["n"], e["all"]["MCR"]["n"])

    def test_the_headline_numbers(self):
        r = self.nums["arms"]["Main"]["runs"]
        self.assertEqual((r["Coff"]["hindi"]["FCR"]["k"], r["Clex"]["hindi"]["FCR"]["k"]), (9, 1))
        self.assertEqual((r["Coff"]["hindi"]["MCR"]["k"], r["Clex"]["hindi"]["MCR"]["k"]), (0, 5))

    def test_committed_generated_files_are_current(self):
        self.assertEqual(NUM.main(["--check"]), 0)

    def test_exclusions_add_a_sensitivity_view_and_never_change_the_primary_numbers(self):
        ex = NUM.build(json.loads(NUM.REPORT.read_bytes()), {"t2p_0002"})
        for arm in ("Main", "Mirror"):
            for tag, e in ex["arms"][arm]["runs"].items():
                self.assertEqual(e["all"], self.nums["arms"][arm]["runs"][tag]["all"])
                self.assertIn("sensitivity_excluding_review_flags", e)

    def test_a_tampered_report_is_refused(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        bad = tmp / "r.json"
        bad.write_bytes(NUM.REPORT.read_bytes() + b" ")
        with self.assertRaises(SystemExit):
            NUM.main(["--report", str(bad), "--check"])


class TestReviewSummary(unittest.TestCase):
    def test_every_row_is_counted_and_only_wrong_or_ambiguous_hindi_pairs_are_excluded(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        review, out = tmp / "review", tmp / "generated"
        review.mkdir()
        rows = [("t2p_1", "correct"), ("t2p_2", "wrong"), ("t2p_3", "ambiguous"), ("t2p_4", ""), ("t2p_5", "Correct")]
        with open(review / "hi_pairs_review.csv", "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["injected_pair_id", "verdict(correct/wrong/ambiguous)", "comment"])
            w.writerows([(i, v, "") for i, v in rows])
        old = REV.REVIEW, REV.OUT
        REV.REVIEW, REV.OUT = review, out
        try:
            REV.main()
        finally:
            REV.REVIEW, REV.OUT = old
        s = json.loads((out / "review_summary.json").read_text(encoding="utf-8"))["hi_pairs_review.csv"]
        self.assertEqual((s["rows"], s["Correct"], s["Wrong"], s["Ambiguous"], s["Unreviewed"]), (5, 2, 1, 1, 1))
        excl = [l for l in (review / "exclusions.txt").read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
        self.assertEqual(excl, ["t2p_2", "t2p_3"])                        # a blank verdict is unreviewed, never "correct", never excluded


class TestPaperChecker(unittest.TestCase):
    def make_paper(self, results_body):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "sections").mkdir()
        (tmp / "generated").mkdir()
        (tmp / "main.tex").write_text("\\newcommand{\\todo}[1]{}\n\\input{sections/results}\n", encoding="utf-8")
        (tmp / "generated" / "numbers.tex").write_text("% GENERATED\n\\newcommand{\\MainCoffFCR}{15/42}\n", encoding="utf-8")
        (tmp / "refs.bib").write_text("@misc{known,\n title={x}}\n", encoding="utf-8")
        (tmp / "sections" / "results.tex").write_text(results_body, encoding="utf-8")
        return tmp

    def run_check(self, paper):
        old = CHK.PAPER
        CHK.PAPER = paper
        try:
            return CHK.main([])
        finally:
            CHK.PAPER = old

    def test_a_clean_paper_passes(self):
        self.assertEqual(self.run_check(self.make_paper("FCR was \\MainCoffFCR{} \\citep{known}.\n")), 0)

    def test_todo_unknown_cite_undefined_macro_and_hand_typed_numbers_fail(self):
        for body in ("\\todo{x}\n", "\\citep{missing}\n", "\\MainCoffFCRtypo{}\n", "FCR was 15/42.\n"):
            self.assertEqual(self.run_check(self.make_paper(body)), 1, body)

    def test_the_real_paper_has_no_undefined_macros_or_unknown_citations(self):
        old = CHK.PAPER
        problems = []
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            CHK.main(["--draft"])
        problems = [l for l in buf.getvalue().splitlines() if "undefined macro" in l or "unknown key" in l or "hand-typed" in l
                    or "not included" in l]
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

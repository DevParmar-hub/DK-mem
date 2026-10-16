# Approval checklist (decisions that need human, written agreement)

Nothing below has been decided. Record: decision, name, date. Until each box is ticked the matching step must not start.

## A. Roles (no person may hold two of: tuner, author, custodian, reviewer)
- [ ] Custodian named (not a tuner; holds the sealed key and the hash log): ______
- [ ] Authors named, one per language, with attested no benchmark exposure: hi ______  mr ______  gu ______
- [ ] Native reviewers named (not the authors, not tuners): hi ______  mr ______  gu ______
- [ ] Tuners listed, including the assistant model used in this repository (it has read the exposed labels): ______
- [ ] Where the append-only hash log lives and who can write to it: ______

## B. Class mix (proposal; the plan fixes none; floors apply per language, after review)
- [ ] gold-different >= 20: kinship >= 8, honorific_register >= 6, contextual_qualifier >= 4
- [ ] gold-same >= 20: kinship >= 6, honorific_register >= 6, name_variant >= 4
- [ ] Accept that contextual_qualifier supports FCR only and name_variant MCR only; class cells below 20 are indicative
- [ ] Or the approved alternative mix: ______

## C. Authoring buffer
- [ ] Authors write >= 26 per language x relation so >= 20 survive review (unchanged target of 20; no padding from dev/reserve data)
- [ ] Accept that a cell still < 20 after review is reported "indicative", not filled up

## D. Replacing the exposed Team B test set (plan §1)
- [ ] The new independent set becomes the held-out set; the exposed 30 stay `dev` (`origin_split: team_b_test_EXPOSED`)
- [ ] The 24-item Hindi reserve set stays unblinded reserve data and is never counted as test
- [ ] `VERIFICATION_PROMPT.md` withdrawn or its label column redacted: ______
- [ ] Freeze is blocked until the new set has passed checks and review

## E. Conventions and conflicts
- [ ] Conventions 1-4 stay in force for authoring, pending native review
- [ ] Conflict deliverable accepted as required (author `conflict` + header `conflict_report`; reviewer resolution or exclusion with reason)
- [ ] A convention rejected for a language triggers a written protocol amendment, not item-level edits

## F. Still open, separate from this package
- [ ] One-seed design accepted in writing (or three seeds required)
- [ ] Config C Marathi/Gujarati judge validated with native-authored cases, frozen first
- [ ] Marathi/Gujarati distractor banks, repaired mr/gu specs and the lexicon sent to native review

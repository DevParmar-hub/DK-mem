# Native-speaker review form (reviewer is not the author and not a tuner)

Reviewer id (pseudonym): ______   Language: ______   Native language / region / dialect: ______   Date (UTC): ______

For every item return one row of `schemas/review_record.schema.json`:
- `relation_correct`: given the two messages and the conventions, is the same/different label right? (`ambiguous` if two readings are defensible)
- `class_correct`: kinship / honorific_register / name_variant / contextual_qualifier correct?
- `natural`: would a native speaker plausibly type these messages? (`yes` / `awkward` / `no`)
- `identifying_or_offensive`: contains a real person's identifying detail or offensive content?
- `conflict_resolution` (REQUIRED on every row): `not_flagged` if the author raised no conflict; otherwise you **must** decide each flagged
  item: `label_stands` (you confirm the author's label and chosen reading are linguistically right, and say why in `reason`) or
  `excluded` (the conflict cannot be resolved, or the label would have to change; say why in `reason`). You may also exclude an
  unflagged item you find ambiguous. Never leave a flagged item without a decision and never relabel it yourself.
- `verdict`: `include` only if relation and class are correct, natural is `yes`, no identifying/offensive content and, for a flagged item,
  `conflict_resolution` is `label_stands`. Everything else `exclude` with a reason. Do not edit items; return them to the author.

Also answer in prose: (1) Is any of conventions 1-4 wrong for your language (state the pairs or patterns affected)? (2) Which items look derived from one frame? (3) Any regional
usage that makes a label region-dependent?
Do not discuss items or labels with anyone who builds or tunes the system.

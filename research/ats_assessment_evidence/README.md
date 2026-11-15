# Evidence files for ATS_WHITEPAPER_FORENSIC_ASSESSMENT.md

Produced 2026-11-15 against commit `50ec2486e18f2d80129dc236913028a9b5794e04`.
These are reviewer-generated artifacts. Nothing here is part of HERALD's production behavior,
and nothing in `herald/` or `Tests/` was modified to produce them.

- `mutate.py` -- pass 1 harness. For each mutant it runs the non-adversarial tests first; if the mutant
  survives, it runs `Tests/test_hulk_100.py` alone. Writes only into scratch copies of the repo.
- `mutate_hulk.py` -- pass 2: `mutate.py` with a `sed` edit so every mutant runs against
  `Tests/test_hulk_100.py` alone. Committed exactly as run.
- `mutation_pass1_nonadversarial_then_adversarial.json`, `mutation_pass2_adversarial_only.json`,
  `mutation_results_combined.json` -- raw per-mutant results.

Re-run (from the repo root, in a venv with `pytest` and `cryptography>=42`):

    python research/ats_assessment_evidence/mutate.py . /path/to/scratch/work out.json 4

Limits: operator set is small (7 operators), equivalent mutants were not eliminated, one run only.
See Section 9 of the assessment.

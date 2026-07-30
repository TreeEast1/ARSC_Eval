# Result artifact index

This directory preserves successful results, negative measurement audits,
failed-run provenance, and independent review memos. Files are indexed here
instead of moved so that hashes and paths cited by the review memos remain
valid.

## Primary five-seed BDD-OIA result

The primary replication uses new paired seeds 43–47. Seed 42 is excluded as
an archival pilot.

- `validity/rq1_multiseed_summary.json`: complete hierarchical-bootstrap
  summary, raw seed metrics, per-class F1, and frozen decisions.
- `validity/rq1_multiseed_seed_metrics.csv`: long-form raw seed estimates.
- `validity/rq1_multiseed_metric_summary.csv`: mean, SD, and hierarchical 95%
  interval for every metric.
- `validity/rq1_seed_43` through `validity/rq1_seed_47`: per-seed training
  logs, calibration results, lossless prediction caches, paired-design checks,
  and paired image-bootstrap metrics.
- `validity/tmux_rq1_multiseed_amendment01.log`: complete successful tmux run.
- `validity/rq1_multiseed_frozen_protocol.json`: pre-result protocol.
- `validity/rq1_protocol_amendment01.json`: independently authorized
  serialization-only amendment and restart boundary.
- `research_review_memo_round4_amendment01.md`: pre-restart independent review.
- `research_review_memo_round5_multiseed.md`: independent post-result review.

Primary decisions:

| Decision | Result |
|---|---|
| Action comparability | PASS: Joint−Action macro-F1 = 0.011536, hierarchical 95% CI [0.001590, 0.021807], inside ±0.03 |
| RQ2-light perturbation subbranch | SUPPORTED: Action−Joint flip = 0.016107, 4/5 seeds positive |
| RQ2 CEG subbranch | UNANSWERED and closed: v2–v5 measurement/population gates failed |

## Metric falsification and C1 measurement validity

- `validity/metric_validity_frozen_grid.json` and `.csv`: frozen
  `{0.3,0.4,0.5,0.6,0.7}` threshold grid.
- `validity/metric_validity_sensitivity.json` and
  `metric_validity_thresholds.csv`: exploratory confidence definitions,
  risk-curve crossings, boundary cases, and implementation sanity checks.
- `validity/perturbation_semantic_audit/audit_summary.json`: model-output-blind
  audit of 100 unique images and 300 transformed pairs; all three
  perturbations passed the ≥0.95 semantic-invariance gate.
- `validity/perturbation_semantic_audit/audit_manifest.csv`: reviewed samples
  and decisions.
- `validity/rq1_amendment01_tests.log` and
  `rq1_amendment01_worker_check.json`: pixel-equivalence and real Windows
  `num_workers=8` checks for the serialization amendment.

Visual audit contact sheets remain local under each `pages/` directory. They
are intentionally excluded from the public Git repository because they
contain redistributed dataset pixels. The manifests, decisions, summaries,
and generation code are tracked.

## Archival seed-42 pilot

The following root-level files predate the new paired-seed replication and
must not be pooled with it:

- `main_results.csv`
- `clean_metrics.json`
- `rationale_metrics.json`
- `safety_metrics.json`
- `consistency_metrics.json`
- `critical_mask_metrics.json`
- `calibration.json`
- `training_log_action_only.csv`
- `training_log_joint.csv`
- `tmux_action_only.log`, `tmux_joint.log`, and the original evaluation logs.

These artifacts are retained for transparency, not treated as confirmatory
five-seed evidence.

## CEG measurement-development record

All v2, v3, and v4 CEG values are excluded from confirmatory claims.

- `validity/mask_audit_v2`: binding audit failed.
- `validity/mask_audit_v3`: binding/contamination audit failed.
- `validity/mask_audit_v4`: the filename-disjoint red/green-light audit failed
  the frozen overall/state-stratified gates; confirmatory CEG was not run.
- `validity/masks_v*_generation.json`,
  `masks_v4_confirmatory_population.json`, and
  `masks_v4_invariants.json`: complete generation and invariant evidence.
- `research_review_memo_round1.md` and
  `research_review_memo_round2_prereg.md`: independent diagnosis and v4
  preregistration.

These negative results validate the measurement gate: the implementation did
not convert a low-quality localization proxy into an ARSC success claim.

## External-data feasibility

- `dataset_scout_round1.md`: one-source dataset screening.
- `validity/vla4codrive_probe_feasibility.json`: sparse public-file technical
  probe.
- `validity/vla4codrive_repository_index.json`: complete repository index
  audit; only nine canonical scenes and at most 2,160 paired windows.
- `research_review_memo_round3_external_prereg.md` and
  `research_review_memo_round4_vla_feasibility.md`: frozen gates and formal
  STOP decision for VLA4CoDrive training.
- `validity/bdd100k_validation_label_overlap.json`: only 53 unseen
  state-matched validation candidates, below the preregistered v5 mask gate.

## Final BDD100K-train v5 CEG stopping record

- `validity/bdd100k_train_v5_metadata_protocol.json`: frozen one-shot
  metadata-only 200/50/50/30 gate.
- `research_review_memo_round6_amendment01.md` and
  `validity/bdd100k_train_v5_protocol_amendment01.json`: independent
  authorization and exact provenance for filtering the transport table to
  original BDD train rows.
- `validity/bdd100k_train_v5_amendment01_pre_gate_check.json`: all five
  conditional restart checks before the only formal gate run.
- `validity/bdd100k_train_v5_metadata_gate.json` and
  `bdd100k_train_v5_candidates.jsonl`: frozen machine result and metadata-only
  proposal manifest.
- `validity/tmux_bdd100k_train_v5_metadata_amendment01.log` and
  `tmux_bdd100k_train_v5_gate_amendment01.log`: successful train-only
  transport and gate logs.
- `research_review_memo_round6_final.md`: final scientific STOP ruling.

The frozen machine decision is `STOP_CEG_INDEPENDENCE` because the analyzer
used `data/raw/lastframe` instead of the actual
`data/raw/lastframe/data` image root, leaving hash independence unevaluated.
The pre-hash proposal upper bound was nevertheless only 87 samples (red 50,
green 37, 87 groups), so no root correction could meet total ≥200 or green
≥50. Independent review therefore also issued
`STOP_CEG_POPULATION_NO_V6`. The pool was not rerun, no masks were generated,
and no proposal logits were read.

## Engineering provenance

- `validity/tmux_rq1_multiseed_attempt01_failed.log`: preserved serialization
  failure before seed-43 test effects/cache were saved.
- `validation_tests.log`: final saved test run.
- `validation_compileall.log`: final bytecode compilation check.
- `validation_verify_outputs.log`: required-output and README command verifier.
- `environment_snapshot.json`: Python, CUDA, GPU, and package versions.
- `reproduction_check.json`: original required-output verifier result.

Downloaded datasets, model checkpoints, detector weights, and audit contact
sheets are intentionally not versioned. Their provenance, hashes where
required, and regeneration commands remain in the tracked configs, scripts,
JSON summaries, and logs.

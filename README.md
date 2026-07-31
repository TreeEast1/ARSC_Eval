# ARSC-Eval on BDD-OIA

This repository evaluates whether four complementary dimensions—Accuracy,
Rationale, Safety, and Consistency (ARSC)—reveal behavior that action accuracy
alone misses. The primary study is a paired five-seed comparison of an
Action-Only ResNet-50 and a Joint Action-Rationale ResNet-50 on the official
BDD-OIA splits.

The repository deliberately retains negative measurement audits and failed-run
provenance. In particular, the critical-evidence-gap (CEG) branch is not
reported as successful because every candidate mask measurement version failed
its frozen visual-quality gate.

## Primary result

Seeds 43–47 are the new primary replication; seed 42 is an archival pilot and
is excluded from the primary mean. Each row below uses 2,000-replicate
hierarchical paired bootstrap intervals that resample training seeds and then
images within selected seeds.

| Dimension / metric | Action-Only | Joint | Joint−Action or Action−Joint | Hierarchical 95% CI |
|---|---:|---:|---:|---:|
| A: Action macro-F1 | 0.674050 | 0.685586 | +0.011536 | [0.001590, 0.021807] |
| R: Rationale macro-F1 | N/A | 0.273589 | N/A | [0.256071, 0.292872] |
| R: Rationale micro-F1 | N/A | 0.503062 | N/A | [0.483546, 0.522462] |
| S: AURC (lower is better) | 0.388824 | 0.372227 | −0.016597 | [−0.033558, −0.000400] |
| S: Unsafe acceptance @90% (lower is better) | 0.490931 | 0.479863 | −0.011068 | [−0.026036, 0.002000] |
| S: calibrated ECE (lower is better) | 0.324007 | 0.324461 | +0.000454 | [−0.020440, 0.016291] |
| C1: mean action flip (lower is better) | 0.118543 | 0.102436 | Action−Joint +0.016107 | [0.001009, 0.032814] |
| C1: Joint rationale Jaccard | N/A | 0.916003 | N/A | [0.908090, 0.926552] |

Frozen decisions:

- Action comparability passed: the complete macro-F1 difference interval lies
  inside the preregistered `[-0.03, +0.03]` equivalence margin.
- The RQ2-light perturbation subbranch is supported: mean
  `Flip(Action)-Flip(Joint)=0.016107`, four of five seeds are positive, and the
  brightness/blur/noise mean advantages are `0.013562`, `0.009173`, and
  `0.025587`, all above the preregistered `-0.01` floor.
- The RQ2 CEG subbranch remains unanswered because the v4 mask measurement
  gate failed. C1 robustness does not establish causal evidence use.

The result supports ARSC as a diagnostic decomposition: action quality and
ranking-based selective risk improve on average, while fixed-coverage risk and
calibration remain uncertain; rationale quality is non-zero but strongly
class-dependent; perturbation stability improves on average but is
heterogeneous across seeds. It does not support a claim that rationale
supervision improves every ARSC dimension or proves causal faithfulness.

## Study design

- Dataset: official BDD-OIA train/validation/test assignment; 4,557 valid
  four-action test samples.
- Actions: Forward, Stop, Left, Right.
- Rationales: the official 21-label BDD-OIA ontology.
- Models: ImageNet-pretrained ResNet-50 with either a four-action head or
  shared-backbone action and rationale heads.
- Pairing: identical backbone/action-head initialization and data order within
  each seed.
- Training: five fixed epochs; checkpoint chosen only by validation action
  macro-F1.
- Thresholds: 0.5 for action and rationale predictions.
- Safety: separate validation-set scalar temperature calibration for both
  models; test data never select temperatures, thresholds, epochs, or seeds.
- C1: lossless in-memory brightness `1.10`, Gaussian blur radius `1.0`, and
  deterministic Gaussian noise `5/255`.
- C1 measurement gate: model-output-blind visual review of 100 images × three
  perturbations; every condition passed the frozen ≥0.95 semantic-invariance
  threshold.
- Uncertainty: paired image bootstrap within seed and hierarchical
  seed-then-image bootstrap across seeds.

The complete frozen protocol, amendment, raw seed values, intervals, and
decisions are in
`outputs/validity/rq1_multiseed_frozen_protocol.json`,
`outputs/validity/rq1_protocol_amendment01.json`, and
`outputs/validity/rq1_multiseed_summary.json`.

## Repository layout

```text
configs/       frozen pilot, validity, and seeds 43–47 configurations
scripts/       download, preparation, training, evaluation, audit, and aggregation entry points
src/           datasets, models, ARSC metrics, bootstrap, and validity utilities
tests/         deterministic metric, perturbation, mask, and feasibility tests
outputs/       primary results, negative audits, review memos, logs, and artifact index
checkpoints/   local resumable checkpoints (gitignored)
data/          downloaded and processed datasets (gitignored)
```

See `outputs/README.md` for the result map and the distinction between primary,
archival, failed-measurement, and external-feasibility artifacts.

## Environment

Python 3.11 and a CUDA-enabled PyTorch build are recommended. Install a
PyTorch/torchvision build suitable for the local GPU, then install runtime or
test dependencies:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

The completed run used an RTX 5090, Python 3.11.13, CUDA 13.0 as reported by
PyTorch, torch `2.10.0.dev20251012+cu130`, torchvision
`0.25.0.dev20251012+cu130`, OpenCV `4.11.0`, and Ultralytics `8.4.45`. The
machine-readable snapshot is `outputs/environment_snapshot.json`.

## Reproduce from scratch

Download and prepare the official last-frame archive:

```powershell
python scripts/download_data.py --data-root data
python scripts/prepare_data.py --config configs/experiment.yaml
python scripts/download_pretrained.py --artifact resnet50
```

Run the preflight checks and low-cost metric validity analyses:

```powershell
python scripts/smoke_test.py --config configs/experiment.yaml --device cuda
python scripts/analyze_metric_validity.py --config configs/experiment.yaml --device cuda
python scripts/build_perturbation_semantic_audit.py --config configs/experiment.yaml
python scripts/summarize_perturbation_semantic_audit.py
```

Run all five paired seeds directly:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_rq1_multiseed.ps1 -PythonExe python
```

For an unattended Windows/WSL run, set the Windows Python executable and start
the portable tmux launcher from WSL:

```bash
ARSC_PYTHON_EXE='D:\path\to\python.exe' bash scripts/launch_rq1_multiseed_tmux.sh
tmux attach -t arsc_rq1_multiseed
```

The successful run in this repository used the independently approved
serialization-only restart in
`scripts/run_rq1_multiseed_amendment01.ps1`. That runner is historical
provenance for this specific run; fresh reproductions should use
`run_rq1_multiseed.ps1`.

### Reproduce the archival seed-42 pilot

These commands regenerate the original pilot artifacts retained at the root of
`outputs/`. They are not the primary five-seed analysis:

```powershell
python scripts/train_model.py --config configs/experiment.yaml --model action_only --device cuda
python scripts/train_model.py --config configs/experiment.yaml --model joint --device cuda
python scripts/calibrate.py --config configs/experiment.yaml --device cuda
python scripts/generate_masks.py --config configs/experiment.yaml --device 0
python scripts/generate_perturbations.py --config configs/experiment.yaml
python scripts/evaluate.py --config configs/experiment.yaml --device cuda
```

## Validate the repository

```powershell
python -m pytest -q
python -m compileall -q scripts src tests
python scripts/verify_outputs.py --config configs/experiment.yaml
```

The current repository check reports 63 passing tests, successful compilation, and all
original required pilot outputs present.

## Measurement and external-data stopping results

- Mask v2 failed critical binding.
- Mask v3 failed binding and control-contamination gates.
- Mask v4 used a filename-disjoint red/green-light population but narrowly
  failed the frozen overall/state gates and contained two rendered-patch shape
  mismatches. Confirmatory CEG was therefore not computed.
- The official BDD100K validation labels yielded only 53 unseen state-matched
  candidates, below the preregistered v5 population gate.
- The final one-shot BDD100K-train v5 metadata intersection produced a
  pre-hash upper bound of 87 state-matched proposals (red 50, green 37). The
  frozen run also used an incorrect image root, so hash independence was not
  established. Because the pre-hash upper bound already fails the frozen
  total ≥200 and green ≥50 gates, independent review formally closed the CEG
  mainline without a rerun or v6.
- VLA4CoDrive was technically readable, but its frozen repository revision
  exposed only nine canonical scenes and at most 2,160 Action/Language paired
  windows. Independent review required stopping external training.

These are informative negative results: they prevent weak evidence
localization or pseudoreplicated external data from being relabeled as metric
validity.

## Frozen-cache metric falsification result

The independently preregistered Round 7 suite reused only the frozen seed
43–47 caches. All 83 exact invariants passed, including exact reproduction of
the Round 5 A/R/S/C1 values. All ten directional controls were positive in
5/5 seeds and had crossed-bootstrap pointwise 95% intervals above zero:

- A original−destroyed Macro-F1: 0.312962 (Action-Only) and 0.320033
  (Joint);
- R original−destroyed Macro-F1: 0.230389;
- S frozen-random−original AURC: 0.137671 and 0.146539, while the separate
  oracle/adversarial ordering gate also passed;
- C1 wrong−correct action flip: 0.669739 and 0.688713; correct−wrong rationale
  Jaccard: 0.782538.

An independent primitive-only reconstruction reproduced every raw value and
all 2,000 crossed-bootstrap intervals with maximum absolute difference 0.
The formal protocol therefore passed, while the independent scientific
verdict remains **PARTIAL**: these are strong BDD-OIA-internal extreme-control
results, not general construct, causal, severity, safety, or external validity.
Six rationale classes remained at F1=0 under both original and destroyed
conditions, and the formal intervals do not cluster neighboring frames by
video clip. The complete hash chain is in
`outputs/validity/arsc_axis_falsification_artifact_index.json`.

## Round 8 graded association-response result

Round 8 replaced the extreme-only Round 7 controls with one outcome-blind,
nested association map at `q={0,0.25,0.50,0.75,1.00}`. It reused the frozen
seed 43-47 prediction caches and performed no training, inference, threshold
selection, mask generation, or data download. Dependence induced by both the
destination and source clips was handled by 1,625 map-closed association
components. Each bootstrap replicate resampled training seeds and one shared
component multiset, then took the weakest expected-direction adjacent step
within each selected seed before averaging.

| Axis | Five-seed mean weakest step | Association-component 95% CI | Positive seeds |
|---|---:|---:|---:|
| A: action Macro-F1 decreases | 0.068671 | [0.059674, 0.072806] | 5/5 |
| R: rationale Macro-F1 decreases | 0.046416 | [0.040571, 0.049523] | 5/5 |
| S: tie-averaged AURC increases | 0.026936 | [0.018370, 0.030091] | 5/5 |
| C1: correspondence degrades | 0.164889 | [0.150002, 0.165152] | 5/5 |

All four preregistered gates passed, and every five-seed mean component curve
had no adjacent reversal. A separate implementation imported no formal metric
code, rebuilt A/R from component-level confusion counts, S from an exact
confidence-tie formula, and C1 from per-image events. It reproduced all point
and 2,000-replicate bootstrap summaries with maximum absolute differences
`1.88e-14` and `2.42e-15`, respectively (7/7 audit checks passed).

![Round 8 graded response curves](outputs/validity/round8_graded_response_curves.png)

The independent scientific verdict is **PARTIAL / BOUNDED INTERNAL
EVIDENCE**, despite a computational/formal **PASS / VALID** verdict. The result
supports graded responsiveness to the frozen association destruction. It does
not establish ontology completeness, rationale grounding or faithfulness,
causal robustness, calibration validity, real-driving safety, or external
validity. Six rationale classes remain F1=0 at every q in every seed; C1 is a
sample-correspondence metric, not a visual-severity or faithfulness metric; and
the inference remains conditional on one map/salt and one BDD-OIA population.
The complete evidence chain is bound in
`outputs/validity/round8_graded_response_artifact_index.json`, with the final
review in `outputs/research_review_memo_round8_final.md`.

## Round 9 20-map robustness result

Round 9 tested whether the Round 8 graded association-response finding depended
on one favorable map/salt. It froze 20 new outcome-blind legal maps before
reading any new q>0 outcome, excluded the historical Round 8 map from the
primary gate, and used a map x seed x per-map-association-component bootstrap.
The formal one-shot run completed as `attempt01`.

| Axis | 20-map grand mean bottleneck | Hierarchical pointwise 95% interval | Positive maps |
|---|---:|---:|---:|
| A | 0.068648 | [0.064261, 0.067624] | 20/20 |
| R | 0.045433 | [0.040589, 0.047385] | 20/20 |
| S | 0.027080 | [0.021644, 0.026686] | 20/20 |
| C1 | 0.163594 | [0.155702, 0.160482] | 20/20 |

All four preregistered gates passed. An independent implementation imported
neither the formal Round 9 analysis nor `arsc_eval`, recomputed all point
diagnostics and all 2,000 hierarchical draws, and passed 8/8 checks. The
maximum point difference was `2.23e-14`; every bootstrap selection and
four-axis value matched exactly, and the formal and independent draw files are
byte-identical.

![Round 9 20-map graded response curves](outputs/validity/round9_multimap_curves.png)

The independent scientific verdict is **BOUNDED CONDITIONAL PASS**. The result
closes the single-map/salt concern for the 20 prefixed maps; it does not turn
those maps into 20 datasets or establish external validity, simultaneous
familywise 95% coverage, rationale faithfulness, calibration validity, causal
evidence, or real-driving safety. Six rationale classes have positive target
support but zero predicted positives and F1 at every map, seed, and q, so the
aggregate R response is driven by the other 15 classes.

The complete evidence chain is in
`outputs/validity/round9_multimap_artifact_index.json`, with the independent
post-result ruling in `outputs/research_review_memo_round9_postresult.md`.
The BDD-OIA salt/map line is now permanently closed.

## Reviewer-bounded next step

CEG remains closed and unanswered. VLA4CoDrive remains
`STOP_EXTERNAL_TRAINING`.

The only authorized successor is the outcome-blind protocol and preflight for
Round 10: a BDD-OIA pixel-space brightness/blur/noise multi-severity
dose-response construct-validation experiment using actual corrupted-image
inference. Exact operators, four nonzero severities per family, semantic
invariance gates, directional estimands, practical thresholds, multiplicity,
clip-cluster resampling, and one-shot failure rules must be frozen before any
new-severity metric outcome is read. A formal run is not authorized until an
independent reviewer gives GO.

## Publishing policy

Raw datasets, checkpoints, detector weights, and visual-audit contact sheets
are not versioned. Numeric results, lossless prediction caches, manifests,
manual decisions, hashes, configs, code, review memos, and complete logs are
versioned. Contact sheets remain local because they contain redistributed
dataset pixels and can be regenerated from tracked manifests and scripts.

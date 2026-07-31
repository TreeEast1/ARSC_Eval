# Round 9 Final Formal-Implementation Review

## Decision

**STOP - FORMAL RUN NOT AUTHORIZED**

No `round9_independent_reviewer_decision.json` is created.

The review was performed against commit:

`16c15286fd3df1221efa320a592b2a368db0031b`

At the start of review, HEAD, `main`, and `origin/main` all pointed to that
commit and the worktree was clean. I did not read or compute any new-map
q>0 metric outcome.

The implementation closes most of the preliminary checklist, but three
formal/governance defects remain. Two are independently sufficient to
block GO.

## Outcome-blind checks that passed

The following frozen artifacts and implementation claims were verified:

- Every input and implementation hash recorded in
  `round9_multimap_formal_implementation_manifest.json` matches the
  current file.
- The formal preflight hash matches its manifest entry.
- The independent structural audit is 13/13 PASS.
- The independent salt replay reconstructs 20/20 cycles and source-map
  stacks exactly without importing the formal construction code.
- The Round 9 map and component artifacts remain unchanged.
- All current formal result, staging-result, reviewer-decision, and
  formal-log paths are absent.
- The complete repository suite passes: 63 tests.
- A separate read-only call of the q0 bridge returned maximum absolute
  difference `0.0`.
- The q0 bridge runs before the formal code opens the new-map source
  arrays.
- The formal CLI exposes only `--preflight-only`; there are no scientific
  parameter overrides.

The primary statistical hierarchy is implemented correctly:

1. One 20-position map draw is made per replicate.
2. One five-position seed draw is shared by every selected map occurrence.
3. Each map occurrence receives its own component draw.
4. The component count and packed membership are taken from the selected
   map's prepared partition.
5. The same component multiset is used for every selected seed, q, model,
   axis, and perturbation inside that occurrence.
6. The bottleneck is computed inside map occurrence and seed before seed
   and map averaging.
7. Repeated seed and map positions retain multiplicity.

The bootstrap and gate constants are also correct:

- 20 maps;
- five seeds;
- 2,000 replicates;
- RNG seed `20260809`;
- four finite axis draw arrays;
- explicit 2.5/97.5 percent linear quantiles;
- strict 18/20 positive-map threshold;
- strict grand mean greater than zero;
- strict CI lower bound greater than zero;
- zero reversal tolerance;
- all four axes required for full PASS.

The point-output arrays include the required A, R, S, and C1 primary
curves; R per-class F1, target support, and predicted-positive counts; all
eight S diagnostics; and individual C1 perturbation diagnostics.

The staging design is mostly sound: all calculations and assertions occur
before staging files are written, final files are promoted only afterward,
and the result JSON is promoted last as the completion marker.

The result claim correctly excludes external validity, independent
datasets, ontology completeness, faithfulness, natural severity,
calibration/safety guarantees, causal evidence, and simultaneous
familywise coverage.

## Blocking defect 1: runtime hash enforcement is incomplete

`reviewer_binding_paths()` does not include all code that the formal
analyzer imports and executes.

It binds:

- `analyze_round9_multimap.py`;
- `multimap_statistics.py`;
- `multimap_response.py`;
- two multimap test files;
- the verifier and launch scripts.

It does not bind at least:

- `src/arsc_eval/graded_response.py`;
- `src/arsc_eval/internal_validity.py`;
- `src/arsc_eval/metric_validity.py`;
- `src/arsc_eval/metrics.py`;
- `src/arsc_eval/constants.py`;
- `tests/test_graded_response.py`.

This is not cured by binding the implementation-manifest file. The formal
runner does not iterate through that manifest and verify every recorded
implementation hash at launch. It verifies `EXPECTED_INPUT_HASHES`, then
checks only the paths returned by `reviewer_binding_paths()`.

Consequently, after a reviewer decision is written, an unreviewed change
to `graded_response.py`, `internal_validity.py`, `metrics.py`,
`metric_validity.py`, or `constants.py` can change formal calculations
without causing `verify_reviewer_go()` to fail.

This breaks the required reviewer-to-runtime hash chain and is a formal GO
blocker.

Required repair:

1. Add every direct and transitive repository code dependency used by the
   formal computation to the frozen implementation manifest.
2. Make the formal runner rehash and verify every implementation-manifest
   entry at launch.
3. Include the same runtime files in `reviewer_binding_paths()`.
4. Bind all formal tests, including `test_graded_response.py`.
5. Add a synthetic test proving that changing any bound runtime dependency
   makes reviewer verification fail.

## Blocking defect 2: the all-zero rationale diagnostic is wrong

The protocol requires reporting all-zero rationale classes together with
per-class F1, support, and predicted-positive counts.

The formal result currently constructs `all_zero_rationale_classes` with:

`rationale_targets[:, class_index].sum() == 0`

That detects classes with zero target support. It does not detect classes
whose per-class F1 is zero across all maps, seeds, and q values.

The frozen Round 8 primitive has no zero-support rationale class:

- minimum target support is 23;
- maximum target support is 1,574;
- the target-zero index list is empty.

Therefore, the current result field is guaranteed to be empty even though
Round 8 already established multiple rationale classes with an all-zero
F1 response caused by zero predicted positives. The underlying
`R_per_class_f1` and `R_predicted_positive_count` arrays are present, but
the required named summary is calculated from the wrong condition and is
misleading.

This does not change the R Macro-F1 gate, but it fails a required
diagnostic and claim-boundary safeguard. It is a formal GO blocker.

Required repair:

1. Define an all-zero F1 class from the completed
   `R_per_class_f1` array across all 20 maps, five seeds, and five q values.
2. Separately report zero-target-support and zero-predicted-positive
   classes; do not conflate them.
3. Assert that the JSON named summary equals the classes derived from the
   stored primitive array.
4. Add a synthetic test with positive target support, zero predicted
   positives, and all-zero F1.
5. Freeze and assert the exact point-diagnostic row count. With the current
   declared loops and columns it should be 60,500 rows.

## Blocking defect 3: direct formal execution can overwrite staging state

The tmux launcher correctly refuses to start when any
`*.attempt01.tmp` staging file exists.

The analyzer's default formal path, however, checks only final artifact
paths. It does not check `STAGING_OUTPUTS` before starting and its write
functions open the same staging paths for replacement.

Thus, if a failed or partial attempt leaves staging evidence, invoking the
analyzer directly can overwrite that evidence under the same authorized
`attempt01` decision. The launch script prevents this normal path, but the
reviewer decision authorizes the analyzer and the analyzer does not enforce
use of the launcher.

Required repair:

- Before reviewer verification or q>0 work, the formal analyzer itself
  must refuse when any final or staging artifact exists.
- Add a test that a pre-existing attempt01 staging file stops the default
  formal path without modifying it.
- Keep the launch-script checks as a second layer.

## Nonblocking notes

- The manifest records `component_count_per_map = 1625`; the formal
  bootstrap also derives each map's count from its prepared partition
  before asserting the frozen artifact fact. This is acceptable and does
  not select or replace a salt.
- The four intervals remain pointwise. The implementation does not claim
  simultaneous familywise coverage.
- The 20 maps remain repeated association realizations on one fixed
  4,557-image population, not 20 independent datasets.
- q0 entries are one repeated identity baseline, not 20 independent clean
  replications.

## Required next state

The repairs above are outcome-independent implementation/governance
repairs. They do not require changing the scientific protocol, maps,
salts, q values, metrics, gates, bootstrap seed, or replicate count.

Before another final review:

1. Commit and push the minimal repairs.
2. Regenerate the q0-only preflight and implementation manifest.
3. Demonstrate 63 plus the new regression tests all pass.
4. Demonstrate two byte-identical preflight/manifest generations on the
   same state.
5. Prove all formal and staging outputs remain absent.
6. Request a new independent final implementation review.

Because no new-map q>0 outcome has been seen and no formal attempt has
started, the future authorized attempt can remain `attempt01` after a new
GO.

## Final verdict

**STOP**

The implementation is close, and its primary hierarchy is correct, but the
runtime hash chain and required all-zero rationale diagnostic are not yet
valid. No formal run is authorized and no GO decision JSON may be created
from this review.

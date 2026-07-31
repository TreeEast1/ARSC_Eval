# Round 9 Final Preregistration Review After STOP01 Repairs

## Decision

**GO**

The Round 9 formal one-shot run is authorized for `attempt01`.

This re-review was limited to the three outcome-independent defects recorded
in:

`outputs/research_review_memo_round9_preregister_stop01.md`

No new-map q>0 metric outcome was read or computed during this review.

Reviewed repository state:

`2eeda1d784c322adf2fa123b9d5c39ad0457d48f`

At review time, HEAD, `main`, and `origin/main` all pointed to this commit and
the worktree was clean.

## Preserved STOP evidence

The original STOP evidence remains preserved:

- STOP01 memo SHA256:
  `C2FFFB1E2D3860A6626E23CF4C5BACE6FA9965F87207EDAD5AA24872DAF61F1E`
- STOP01 preflight SHA256:
  `222252E3776A35F68D356E173753A479CAAADA45E367F9BA7076AEF118FEF021`
- STOP01 implementation manifest SHA256:
  `2F338F02F0298BDAF61FD1BFA5331E093AF7A1B15052E9789293180BFAAB4902`

The replacement freeze is:

- Current preflight SHA256:
  `A0F716F0887B00A032734F040BB487087D2F114719B5EC0AD046149870596BA6`
- Current implementation manifest SHA256:
  `A7B50C8339EAAB39D2758FA296189A367997630D21BB07B84076242BF0335178`

## Repair 1: complete runtime hash chain

**PASS**

The formal implementation manifest now binds:

- `analyze_round9_multimap.py`;
- `multimap_statistics.py`;
- `multimap_response.py`;
- `graded_response.py`;
- `internal_validity.py`;
- `metric_validity.py`;
- `metrics.py`;
- `constants.py`;
- all three relevant formal/graded-response test files;
- both independent verifier scripts;
- the tmux launch script.

This covers every repository module imported by the formal analyzer and the
transitive `arsc_eval` imports used by those modules.

`reviewer_binding_paths()` now includes the same executed dependencies and
tests, as well as all frozen inputs, audits, preflights, manifests, and prior
review memos.

`verify_reviewer_go()` now performs two independent runtime checks:

1. It hashes every path in `reviewer_binding_paths()` and compares it with
   the reviewer decision.
2. It opens the frozen implementation manifest and rehashes every
   `implementation_hashes` entry.

Therefore a post-review change to any executed repository dependency fails
before q0 verification or q>0 computation.

All current input, implementation, and preflight hashes recorded in the
manifest match their files exactly.

## Repair 2: correct all-zero rationale diagnostic

**PASS**

`all_zero_rationale_classes` is now derived from:

`R_per_class_f1[map, seed, q, class]`

A class is included only if every saved F1 value across all 20 maps, all five
seeds, and all five q values is exactly zero.

`zero_support_rationale_classes` is calculated separately from target
support. The implementation no longer conflates an all-zero F1 response with
zero target support.

The stored primitive array remains the source for the named all-zero summary,
so the result JSON and independently inspectable `R_per_class_f1` artifact
have the same definition.

This repair does not change the R Macro-F1 primary statistic or gate.

## Repair 3: direct-run staging refusal

**PASS**

Before reviewer verification, q0 work, map loading, or any q>0 computation,
the default formal path now requires absence of:

- every final formal artifact; and
- every `attempt01` staging artifact.

The analyzer itself now refuses a stale staging path. The tmux launcher keeps
its independent final/staging/log refusal checks as a second layer.

Thus a failed or partial attempt cannot be silently overwritten under the
same `attempt01` authorization.

## Regenerated preflight

The current preflight reports:

- status `PASS_AWAITING_INDEPENDENT_REVIEWER_GO`;
- all frozen input hashes match;
- independent structural audit PASS;
- independent salt-to-cycle-to-map replay PASS;
- all formal and staging outputs absent;
- 63 tests PASS;
- complete Round 8 q0 bridge PASS;
- q0 maximum absolute difference `0.0`;
- no new-map q>0 source row read;
- no new-map q>0 metric outcome computed;
- formal run not yet permitted without this reviewer decision.

A separate read-only q0 bridge invocation during STOP01 review also returned
maximum difference `0.0`. This re-review did not invoke the formal analyzer
or load new-map q>0 source rows.

## Current output absence

Immediately before this GO memo and decision were created, the following
were absent:

- formal result JSON;
- formal primitive NPZ;
- bootstrap draw NPZ;
- point diagnostic CSV;
- bootstrap summary CSV;
- all corresponding `attempt01.tmp` staging paths;
- formal tmux log;
- prior GO decision JSON.

The GO memo and decision are authorization artifacts, not metric outcomes.

## Unchanged scientific and statistical contract

The STOP01 repairs are implementation/governance repairs only. They do not
change:

- the 20 prefixed maps or salts;
- the five training seeds;
- q or active-image counts;
- threshold 0.5;
- A, R, S, or C1 definitions;
- tie-averaged AURC;
- per-map/per-seed-first bottleneck order;
- 18/20 positive-map gate;
- no-reversal gate;
- 2,000 hierarchical bootstrap replicates;
- bootstrap seed `20260809`;
- pointwise linear percentile intervals;
- all-four-axis full PASS rule;
- failure and no-salt-replacement rules.

The future result remains conditional on one fixed 4,557-image BDD-OIA
population. Twenty maps are not twenty datasets, q0 is not twenty independent
clean replications, and the intervals are not simultaneous familywise 95%
intervals.

## Authorization conditions

This GO authorizes exactly one run:

- authorized attempt: `attempt01`;
- formal run count: one;
- required launcher: the frozen tmux launch script;
- maps: 20;
- seeds: 5;
- replicates: 2,000;
- bootstrap seed: `20260809`.

The run must stop if any reviewed hash differs, any final or staging output
already exists, the reviewer decision differs from the machine schema, the q0
bridge fails, or any pre-result assertion fails.

If attempt01 stops before publishing the completion-marker result JSON, its
log and any staging evidence must be preserved and an independent failure
review is required before any retry.

## Final verdict

**GO - ROUND 9 FORMAL ATTEMPT01 AUTHORIZED**

All three STOP01 blockers are closed, q0-only preflight remains PASS, and no
new-map q>0 outcome has been seen.


# Nuclear Transfer Conditions

## Status of this document

This is a **conditions statement, not a result**. No nuclear experiment was
performed, no nuclear plant data was used, and none is planned within this
work. The purpose is to state precisely what would have to be established
before the ARSC protocol could be applied to nuclear power plant (NPP)
decision support, and to make the boundary of the existing evidence explicit.

The single most important sentence in this document:

> The BDD-OIA study demonstrates **protocol mechanics** and **multi-axis
> diagnostic value**. It is **not nuclear safety validation.**

Nothing in the driving experiments may be presented as evidence about nuclear
safety, reactor operation, or operator decision quality.

## Why a transfer statement is needed at all

ARSC's contribution is a *reporting discipline*: evaluate a decision model on
several non-redundant axes and report them separately rather than as one score.
That discipline is domain-independent in form. The **measurements** that
instantiate it are not. Each of the four axes carries domain assumptions that
BDD-OIA satisfies and a nuclear setting would not.

The table below summarises; the sections after it give the required conditions
per axis.

| Axis | Transfers directly? | What must be rebuilt first |
| --- | --- | --- |
| A - Action Performance | Yes, in form | Define the nuclear task label set (accident identification / operational decision) and its class balance |
| R - Rationale-label Performance | No | A nuclear-domain evidence/rationale ontology; the 21 BDD-OIA reasons do not transfer |
| S - Selective Risk & Calibration | Partly | Redefine confidence and episode correctness for the nuclear task, then recalibrate |
| C - Prediction Stability | No | Perturbations derived from real instrumentation assumptions, not brightness/blur/noise |

## A - Action Performance

**Transfers directly in form.** A is a task-performance measurement on a
discrete decision output, and an NPP decision-support task has the same shape:
accident or transient identification, or selection of an operational decision.

Conditions:

1. Define the decision label set explicitly (for example accident type
   classification, or a discrete set of operator actions), with the same care
   about multi-label vs single-label structure that BDD-OIA's four-action set
   required.
2. State the class balance and the base rate of each decision. Macro-F1 on a
   severely imbalanced nuclear label set will behave very differently from
   BDD-OIA's.
3. Fix the decision threshold and its justification before evaluation, as the
   0.5 threshold was fixed here.
4. Report the practical-equivalence margin for the nuclear task. The +/-0.03
   margin used here is specific to this study and carries no nuclear meaning.

## R - Rationale-label Performance

**Does not transfer.** The 21 BDD-OIA rationale labels ("red_light",
"obstacle", "no_left_lane", and so on) have no nuclear analogue and must not be
mapped onto one.

Conditions:

1. **Build a nuclear-domain evidence/rationale ontology first.** Plausible
   element types include key measurement points and their identifiers, trend
   directions and rates for those measurements, alarm and setpoint crossings,
   and specific EOP (Emergency Operating Procedure) entries or steps.
2. Establish who annotates that ontology and with what reliability. BDD-OIA's
   rationale labels are crowd/annotation artifacts; EOP-grounded rationales
   would need procedure-anchored ground truth and inter-annotator agreement.
3. Establish ontology coverage explicitly. This work did **not** establish
   ontology completeness even for BDD-OIA, and the coverage holes found here
   (six of twenty-one classes never recovered) show that per-class reporting is
   mandatory, not optional.
4. Retain the terminological boundary: even with a nuclear ontology, R would
   measure **rationale-label recovery**, not reasoning faithfulness and not
   whether the model used the correct physical evidence.

## S - Selective Risk & Calibration

**The mechanism transfers; the operationalisation does not.** Selective
prediction and abstention are directly meaningful in NPP decision support,
where deferring to a human operator is an available and often preferred action.

Conditions:

1. **Redefine correctness at the right granularity.** BDD-OIA's S uses an
   exact-set error over four action bits on a single frame. A nuclear task is
   naturally *episodic*: correctness should be defined over a transient or
   event episode, with the timing of the decision included, not over an
   isolated instantaneous sample.
2. **Redefine confidence to match that correctness event.** The construct audit
   in this work is the cautionary evidence: pairing an exact-set error with a
   single-bit `max(p)` confidence produced an ECE of about 0.324 where a
   semantically matched proxy produced about 0.099 on identical predictions. A
   nuclear deployment must not inherit that mismatch.
3. **Recalibrate on nuclear data.** Temperature scaling fitted on BDD-OIA
   validation frames carries no information about an NPP model.
4. **Set the operating point from the domain, not from convention.** UAR@90
   encodes a 90% coverage choice with no nuclear justification. The acceptable
   coverage, and the cost asymmetry between a missed identification and an
   unnecessary abstention, must come from safety analysis.
5. Continue to report AURC, UAR-type risk and calibration error separately.
   This work found they disagree with each other under every confidence
   construction tested; there is no reason to expect agreement in a nuclear
   setting.
6. Retain the terminological boundary: S is a selective-prediction operating
   characteristic. It is not "Safety" and must not be renamed as such,
   especially in a nuclear context where "safety" has a regulatory meaning.

## C - Prediction Stability under perturbation

**Does not transfer.** Brightness, Gaussian blur and Gaussian pixel noise are
meaningless for plant instrumentation signals and must not be carried over.

Conditions:

1. **Derive the perturbation family from real instrumentation assumptions.**
   The perturbations must be justified by the measurement chain, for example:
   * sensor accuracy class and calibration uncertainty;
   * measurement noise characteristics of each channel;
   * sensor drift over the fuel cycle or since last calibration;
   * missing or dropped channels, and failed or frozen sensors;
   * temporal delay, sampling jitter, and communication latency;
   * quantisation and transmitter range limits.
2. **Preserve the semantics-preserving requirement explicitly.** A perturbation
   qualifies only if the correct decision is provably unchanged. For plant
   signals this must be argued against the physics and the procedure, not
   assumed as it can be for a mild brightness change on a photograph. A
   perturbation large enough to change the correct diagnosis is not a stability
   test.
3. **Define severity levels in engineering units** (percent of span, multiples
   of the accuracy class, seconds of delay), not in arbitrary units.
4. **Choose the stability quantity to match the decision.** Action-set flip
   rate on a frame becomes, for an episodic task, something like decision
   changes per episode or time-to-decision instability.
5. Retain the terminological boundary: even a well-designed nuclear C axis
   measures prediction stability under a stated perturbation model. It is not
   evidence faithfulness, and it is not a robustness guarantee against
   conditions outside that model.

## Cross-cutting conditions

Beyond the per-axis requirements, a nuclear transfer would need:

1. **A data regime that supports the claim.** The seed heterogeneity found here
   - where no headline comparison was unanimous across five training seeds -
   implies that any nuclear evaluation must report seed-level and
   run-level distributions, not means alone.
2. **Pre-registration with domain-justified thresholds.** The thresholds in
   this work (+/-0.03 equivalence, 0.01 effect gates, 90% coverage) are study
   conventions, not safety criteria.
3. **Validation and licensing context.** ARSC is an evaluation and reporting
   protocol. It is not a verification and validation methodology, does not
   satisfy any regulatory qualification requirement, and produces no safety
   case.
4. **Explicit treatment of the human operator.** In NPP decision support the
   model is an advisor. Evaluating the model alone omits the operator-model
   system, which is where the actual decision quality lives.

## What this work does establish for a future nuclear effort

Stated conservatively, and only as protocol-level findings:

1. Reporting several evaluation axes separately is *operationally* different
   from reporting a single task metric: it changed the judgement in a case
   where the task metric was practically equivalent.
2. Prediction-set stability and aggregate task performance can diverge sharply
   - large numbers of per-sample decision changes with almost no movement in
   aggregate Macro-F1. Any nuclear evaluation relying on an aggregate metric
   alone is exposed to that blind spot.
3. Selective-risk conclusions are sensitive to how confidence is
   operationalised, so the confidence definition must be justified against the
   correctness event rather than chosen by convention.
4. Per-class reporting is necessary: an aggregate rationale score concealed
   complete non-recovery of six label classes.
5. Training-run heterogeneity can reverse axis-level conclusions, so
   single-run evaluations are insufficient.

None of these five points is a statement about nuclear safety. They are
statements about how to *measure* a decision model.

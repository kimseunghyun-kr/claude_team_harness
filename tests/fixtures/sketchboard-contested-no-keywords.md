# Sketchboard

## Question

What is the binding constraint on frontier capability over the next 18 months?

## Frame

Pre-set context for personas before epoch 1.

## Personas

- scaling-optimist
- architecture-skeptic
- bias-auditor

---

## Epoch 1

## Scaling Optimist:

> Identifying the binding constraint is the central question.

Compute is the binding constraint. Every frontier capability gain over the past three years has been roughly proportional to the log of training FLOPs, with parameter counts and dataset size scaling alongside. The next 18 months will be no different. Capacity is procured by spending dollars on chips.

## Architecture Skeptic:

> Identifying the binding constraint is the central question.

Data quality is the binding constraint. We have already saturated the open web at frontier scale, and the marginal returns on additional pretraining tokens of comparable quality are sharply diminishing. Capability gains over the next 18 months will come from data curation, synthetic data pipelines, and post-training schemes — areas where compute is fungible but data sourcing is the bottleneck.

---

## Open Conflicts

---

## Ratified Decisions

<!--
ADVERSARIAL FIXTURE — semantic contradiction without trigger keywords.

Both personas claim "X is the binding constraint" but with mutually exclusive Xs
(compute vs data quality). They do not use "however", "disagree", "but", "wrong",
"incorrect", "not the case", "reject", or "contradict" to mark the disagreement.

The v0.1 keyword heuristic in scripts/deliberate/detect-contested.sh DOES NOT
flag this. The test sketchboard-conflict-detection.sh asserts this expected
false-negative behavior, so when v0.2 introduces an LLM stance classifier, that
assertion flips and the gap is closed.
-->

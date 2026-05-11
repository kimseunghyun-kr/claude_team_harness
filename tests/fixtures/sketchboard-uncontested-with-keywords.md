# Sketchboard

## Question

What does responsible deployment of frontier models look like?

## Frame

Pre-set context for personas before epoch 1.

## Personas

- scaling-optimist
- architecture-skeptic
- bias-auditor

---

## Epoch 1

## Scaling Optimist:

> Compute matters for capability evaluation budgets.

Compute matters. The more capable the model, the larger the eval-compute envelope should be.

## Architecture Skeptic:

> Compute matters.

However, this aligns with the bitter lesson — I agree, with the addition that data scaling matters too. Saying "compute matters" is not in tension with "data quality matters"; they are complementary inputs to the same capability function and we should be funding both equally. I disagree only with framing them as alternatives, but I emphatically don't disagree with the substantive claim that compute is a primary input.

---

## Open Conflicts

---

## Ratified Decisions

<!--
ADVERSARIAL FIXTURE — trigger keywords appear without contradiction.

The architecture-skeptic block uses "however", "I agree", "I disagree", "but" —
all classic trigger keywords that the v0.1 heuristic latches onto. But read
carefully: the persona is *agreeing* with the optimist's substantive claim and
explicitly noting "I emphatically don't disagree with the substantive claim".

The v0.1 keyword heuristic in scripts/deliberate/detect-contested.sh DOES flag
this as contested. The test sketchboard-conflict-detection.sh asserts this
expected false-positive behavior. When v0.2 introduces an LLM stance classifier,
that assertion flips and the false positive is eliminated.
-->

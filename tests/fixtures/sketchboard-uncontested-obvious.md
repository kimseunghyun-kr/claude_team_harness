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

> Responsible deployment depends on capability evaluation.

Capability evaluation should scale with model capability. Compute-budgeted red-teaming is a useful primitive: the more capable the model, the more compute we should spend probing for failure modes before release.

## Architecture Skeptic:

> Compute-budgeted red-teaming is a useful primitive.

This complements architectural-side defenses. We can also use targeted probes that exploit known inductive biases of the architecture to find failure modes that pure black-box compute would miss. The two approaches stack rather than compete.

---

## Open Conflicts

---

## Ratified Decisions

# Sketchboard

> Deliberation HEAD. Personas read this in full before each turn. The chair ratifies what becomes canonical at epoch boundaries.
>
> This is **not** Plans.md. Plans.md tracks tasks; Sketchboard tracks the deliberation itself.

## Question

Does scale alone produce AGI?

## Frame

<!-- The chair sets shared context here before epoch 1 starts. Personas treat this as agreed-upon. -->

(chair to fill before run, or leave blank)

## Personas

<!-- Declared persona ids for this deliberation. Synced from harness.toml [deliberation].personas. -->

- scaling-optimist
- architecture-skeptic
- bias-auditor

---

## Epoch 1

<!-- Persona blocks accumulate below as the bidding loop runs.
     Each block must use the form:

       ## <Persona Name>:
       <body — must quote at least one earlier sketchboard claim>

     Personas never edit another persona's block, never edit ## Ratified Decisions. -->

## Scaling Optimist:

> Does scale alone produce AGI?

Start with the bitter lesson: every decade, hand-designed structure has lost to general methods that exploit more compute, and there is no published evidence that frontier capability has decoupled from this trend. Chinchilla pinned down compute-optimal scaling laws (parameters and tokens must scale together; most "novel architectures" lose their edge once you re-run the comparison at matched FLOPs), GPT-4 and Gemini Ultra extended the same loss-curve another order of magnitude with predictable emergent capabilities, and Kaplan et al. 2020 already showed the loss vs. compute curve is shockingly clean across seven orders of magnitude. I concede scale does not buy you alignment guarantees, mechanistic interpretability of the resulting network, or sub-watt edge inference — those are genuinely orthogonal axes and I will not pretend otherwise. But to the architecture-skeptic who will inevitably argue that some missing inductive bias blocks AGI: name the capability you think is blocked, and tell me what it looks like at 10x training compute and 100x inference compute before you reach for a new module — because historically that prediction has been wrong every single time.

## Architecture Skeptic:

> name the capability you think is blocked, and tell me what it looks like at 10x training compute and 100x inference compute before you reach for a new module

Yes, and I'll name one: length-generalization on algorithmic reasoning over variable-depth structure — parity and addition past training length, propositional SAT near the phase transition (clause/variable ratio ~4.26), and shortest-path queries on graphs whose diameter exceeds anything in the training distribution. Dense Transformers plateau here with disturbing flatness; Anil et al. 2022 and the Faith-and-Fate work (Dziri et al. 2023) show that even at substantial scale, accuracy on n-digit multiplication and compositional graph traversal collapses as soon as n exceeds training depth, and the curve does not bend with another order of magnitude of compute. Meanwhile a single architectural change — Universal Transformer with adaptive halting, or a pointer/Graph Network with explicit relational message-passing — produces step-changes on the *same* compute budget on those exact tasks; that pattern is the same one we already saw when attention replaced RNNs on long-range copy, when MoE broke the dense-FLOPs frontier per active parameter, and when retrieval gave small models capabilities that 100x dense scaling had not. I will narrowly concede Sutton: at fixed architecture inside the regime where the architecture is already well-matched to the task (commodity next-token prediction on web text), scale dominates and most hand-designed gadgets evaporate at matched FLOPs. The disagreement is the universal quantifier — "scale alone" smuggles in "across all capabilities," and the algorithmic-reasoning curves are the specific counterexample that 10x doesn't fix.

---

## Open Conflicts

<!-- Auto-populated by `/harness-deliberate review` when contested sections are detected.
     Format:
       ### Epoch <N> — <section title>
       - <persona-a>: "<quoted claim>"
       - <persona-b>: "<contradicting quoted claim>"
     The chair resolves conflicts via ratify / request-revision / edit-and-ratify. -->

---

## Ratified Decisions

<!-- Chair-only. Moved here when an epoch is ratified.
     Personas MUST NOT edit this section. The postcheck script enforces this. -->

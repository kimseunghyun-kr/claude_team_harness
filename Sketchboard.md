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

## Scaling Optimist:

> a single architectural change — Universal Transformer with adaptive halting, or a pointer/Graph Network with explicit relational message-passing — produces step-changes on the *same* compute budget on those exact tasks

Every example you just listed is a *scaling-pressure* discovery, not a refutation of scale. Attention itself came out of Bahdanau et al. 2014 trying to push seq2seq past the fixed-vector bottleneck that scaling RNN encoders alone could not break — attention was found *because* people were scaling and hit a wall, and the same is true of MoE (compute-equivalent dense was getting prohibitive) and Graph Networks (reported and benchmarked in compute-matched terms because that's the only frame the field accepts now). On length-generalization specifically: the picture moved sharply once positional encoding was fixed — RoPE and its NTK-aware / YaRN variants 2023-24, plus chain-of-thought and self-consistency at inference-compute scale, have shown n-digit multiplication and multi-hop reasoning curves that *do* bend with compute when the positional substrate isn't artificially capped at training length. I concede the Faith-and-Fate result narrowly: at fixed positional encoding and zero inference-compute scaffolding, dense Transformers do plateau on compositional depth — but that is a statement about a specific frozen configuration, not about the scaling axis. Name the capability that survives RoPE-class positional fixes *and* 100x inference compute and still flatlines, and then we have a real architectural counterexample.

## Architecture Skeptic:

> Every example you just listed is a *scaling-pressure* discovery, not a refutation of scale.

This move makes the scaling thesis unfalsifiable: if every architectural win retroactively counts as scale's victory "because scaling pressure motivated the search," then scale-alone survives every conceivable outcome and has stopped paying rent in pre-registered predictions. Notice the asymmetry — Kaplan 2020 and Chinchilla cash out as numerical power-laws fit *before* the next training run, and they get falsified when a run lands off-curve; "scale explained that retrospectively" cannot be falsified by any experimental result, because the motivational ORIGIN of an idea is independent of the MECHANISM that makes it work (attention works because of the all-pairs interaction kernel, not because Bahdanau was frustrated). I'll concede positional encoding narrowly: yes, fixed sinusoidal PE was the binding constraint on length-extrapolation, and RoPE/YaRN move the curve — but "the right inductive bias for this domain was wrong and someone fixed it" is exactly the architectural claim, dressed in scaling clothes. So here is the pre-registration I want: give me a Kaplan-style power-law prediction, written down now, for accuracy on n-digit multiplication and SAT-near-phase-transition at the next 10x training compute *and* 100x inference compute, under a frozen RoPE-class config — if the curve bends as you predict, you win cleanly; if it flatlines, "scaling pressure motivated the fix" doesn't get to retroactively claim the next architectural patch.

## Scaling Optimist:

> if every architectural win retroactively counts as scale's victory "because scaling pressure motivated the search," then scale-alone survives every conceivable outcome and has stopped paying rent in pre-registered predictions

Conceded — the "scaling pressure motivated it" move was doing too much retrospective work, and you're right that motivational origin and mechanism are separate claims I was conflating. What scaling actually pre-registered, and should be held to, is narrower: Kaplan 2020 and Chinchilla power-law fits that called GPT-4 and Gemini Ultra cross-entropy and downstream benchmark numbers within published error bars *before* those runs landed, plus the emergent-threshold predictions (in-context learning at ~10^22 FLOPs, multi-digit arithmetic, chain-of-thought eliciting reasoning at scale) that were named in advance and showed up on schedule. I'll hold the scaling claim to that pre-registered version — compute-loss curves and threshold predictions on next-token-prediction-shaped tasks — and stop using it to absorb every architectural step-change post hoc; whether algorithmic length-generalization needs a genuine architectural step (not a positional-encoding patch) stays a live open question, and I won't pre-claim it for scale.

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

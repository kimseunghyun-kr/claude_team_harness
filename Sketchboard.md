# Sketchboard

> Deliberation HEAD. Personas read this in full before each turn. The chair ratifies what becomes canonical at epoch boundaries.
>
> This is **not** Plans.md. Plans.md tracks tasks; Sketchboard tracks the deliberation itself.

## Question

Does scale alone produce AGI?

## Frame

<!-- Chair-set context. Personas treat this as agreed-upon. -->

Smoke test of v0.1 deliberation harness. Three personas declared: scaling-optimist, architecture-skeptic, bias-auditor. Default budget = 5; smoke run uses budget = 3 for brevity.

## Personas

- scaling-optimist
- architecture-skeptic
- bias-auditor

---

## Epoch 1

<!-- Persona blocks accumulate below as the bidding loop runs. -->

## Scaling Optimist:

> Does scale alone produce AGI?

The scale-pilled view here is: the framing buries the question by smuggling in "alone" as if compute arrives without data curation, optimizer choices, and training recipes — none of which are architectural in the Sutton sense. Chinchilla showed we were undertrained by roughly 4x; GPT-4 and Gemini Ultra are existence proofs that capability tracks training-compute across orders of magnitude, with emergent behaviors landing roughly where Kaplan/Hoffmann curves predicted. So my move is to reframe: the live question isn't "scale vs. something else" but "what does this look like at 10x compute?" — and the historical answer has been "most claimed walls dissolve." I will concede up front where scale genuinely doesn't apply: alignment guarantees, mechanistic interpretability, and sample-efficient on-device inference are not compute-bound in the same way. But for the AGI question as posed, the burden of proof sits with whoever claims a capability that scaling laws predict but that 10x compute would fail to deliver. Name one, concretely, and we have a real debate.

## Architecture Skeptic:

> Name one, concretely, and we have a real debate.

Yes, and also — long-horizon algorithmic reasoning over discrete structures, specifically graph problems where the solution requires composing O(n) steps of pointer-chasing or constraint propagation (think shortest-path on adversarially-chosen graphs, or SAT instances near the phase transition). The empirical record here is not subtle: dense transformers plateau on length generalization even with 10-100x compute scaling, while a single architectural change — replacing softmax attention with a recurrent or pointer-based inductive bias (Neural GPUs, Graph Networks, the Universal Transformer's adaptive halting) — produces step-change improvements on the *same* compute budget. The closest historical parallel is attention itself: RNNs didn't get to GPT-3 by scaling, they got replaced. MoE is a second case — sparsely-gated routing gave you a 7x effective-parameter multiplier that no amount of dense scaling reproduced on equal FLOPs. I concede the Sutton point that hand-crafted features lose to learned ones; my claim is narrower, which is that the *macro-architecture's compositional shape* (recurrence, sparsity, retrieval, structured attention) is itself a learned-vs-imposed choice where the imposed version wins on specific capability axes. So the real debate isn't "scaling delivers everything" vs. "scaling delivers nothing" — it's whether the next 1-2 step changes on the road to AGI look more like Chinchilla's recipe tweak (pure compute story) or more like the attention-to-RNN transition (architectural story). I'd bet at least one of the next three falls in the latter bucket.

## Scaling Optimist:

> RNNs didn't get to GPT-3 by scaling, they got replaced. MoE is a second case — sparsely-gated routing gave you a 7x effective-parameter multiplier that no amount of dense scaling reproduced on equal FLOPs.

This is the strongest version of the architectural case, and it actually undercuts itself: attention was discovered by Bahdanau et al. trying to scale seq2seq past the fixed-vector bottleneck, and "Attention Is All You Need" was a scaling-throughput paper before it was a capability paper — they removed recurrence because recurrence didn't parallelize on the hardware they wanted to throw at it. MoE is even cleaner as a counterexample to your framing: Shazeer's 2017 paper is literally titled "Outrageously Large Neural Networks," it exists because dense scaling was getting expensive, and every subsequent MoE result (Switch, GShard, Mixtral) is reported in compute-equivalent terms. So the step changes you name are compute-enabled discoveries, not compute-independent ones — they're what scaling pressure produces when a bottleneck binds. On your long-horizon graph example: length-generalization has been shown to track scale once you fix positional encoding (Anthropic's and DeepMind's 2024-25 work on RoPE variants and chain-of-thought length scaling), so the "plateau" you cite is a recipe artifact, not a ceiling. I'll take your bet on the next three step changes — but score me a win if the architectural change in question was itself motivated by a scaling bottleneck, because that's the pattern.

## Architecture Skeptic:

> So the step changes you name are compute-enabled discoveries, not compute-independent ones — they're what scaling pressure produces when a bottleneck binds.

This reframe is unfalsifiable in the way that hurts predictive content: if every architectural step change retroactively becomes "scale was the real cause because scaling pressure motivated it," then the scaling hypothesis has stopped paying rent in advance predictions and has become an interpretive lens applied after the fact. Note the asymmetry — "scaling laws" cash out as pre-registered quantitative forecasts (Kaplan, Chinchilla; loss as a power-law in N, D, C), whereas "scale explained that retrospectively" makes no commitment before the discovery and survives any outcome. The motivational origin of an idea is independent of whether the *mechanism* it introduced is compute-substitutable: Bahdanau being motivated by a bottleneck doesn't mean dense recurrence at 10x FLOPs would have reached attention-equivalent capability, and that counterfactual is the one your hypothesis owes. I'll concede the positional-encoding point narrowly — yes, fixed PE matters for length generalization — but "fix the inductive bias for this domain" is itself the architectural claim I'm making; calling the fix a recipe tweak doesn't dissolve it, it just renames it. So the operational test stands: name a pre-registered scaling-law prediction for long-horizon algorithmic reasoning at the next 10x, and if the prediction misses while a structural change closes the gap, that's the architectural story you keep promising will never appear.

---

## Open Conflicts

<!-- Auto-populated by /harness-deliberate review. -->

---

## Ratified Decisions

<!-- Chair-only. -->

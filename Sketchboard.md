# Sketchboard

> Deliberation HEAD. Personas read this in full before each turn. The chair ratifies what becomes canonical at epoch boundaries.
>
> This is **not** Plans.md. Plans.md tracks tasks; Sketchboard tracks the deliberation itself.

## Question

How does Low-Rank Adaptation (LoRA) change the scale-vs-architecture discussion? Should we compress the latent vector more (accepting information loss), or discard that assumption and pursue alternatives that make KV cache more mobile for scale?

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

## Architecture Skeptic:

> How does Low-Rank Adaptation (LoRA) change the scale-vs-architecture discussion? Should we compress the latent vector more (accepting information loss), or discard that assumption and pursue alternatives that make KV cache more mobile for scale?

Yes, and also: LoRA is the wrong abstraction layer for the question being asked. LoRA is a compression of weight *updates* during fine-tuning — it says nothing directly about latent-vector compression at inference, and even less about KV cache mobility. The framing question silently fuses three problems with three different inductive biases: (a) weight-delta compression (low-rank vs block-sparse vs quantized adapters), (b) activation/KV compression (SSM-style recurrent state vs sliding-window attention vs grouped-query / multi-query attention), and (c) "mobility" of context across devices or sessions (retrieval, external memory, paged KV). I'll concede compute matters and that at fixed architecture more FLOPs help — but each of those three sub-problems carries an architectural choice that compute does not dissolve, because each choice fixes a different inductive bias about what is redundant in the signal.

So "compress the latent more vs find KV alternatives" is a false binary. The real question is which inductive bias matches which deployment regime: long-context retrieval workloads reward external memory, on-device inference rewards GQA + quantization, continual-adaptation workloads reward low-rank deltas. Treating LoRA as the lens through which to ask any of these collapses three different decisions into one — and that's exactly the move where "scale will sort it out" tends to smuggle in a fixed architecture.

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

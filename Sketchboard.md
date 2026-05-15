# Sketchboard

> Deliberation HEAD. Personas read this in full before each turn. The chair ratifies what becomes canonical at epoch boundaries.
>
> This is **not** Plans.md. Plans.md tracks tasks; Sketchboard tracks the deliberation itself.

## Question

how does Low rank adaptation change the scale vs architecture discussion? should we compress the latent vector more which may incur loss in data, or should we discard that assumption and try to find alternatives to make KV cache more mobile for scale

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

> how does Low rank adaptation change the scale vs architecture discussion? should we compress the latent vector more which may incur loss in data, or should we discard that assumption and try to find alternatives to make KV cache more mobile for scale

LoRA is a case study that cuts directly against the "just scale it" framing. The insight behind LoRA is that fine-tuning updates lie in a low-dimensional subspace — rank 4 or 8 suffices where the full parameter space is millions-dimensional. That is an inductive bias claim, not a compute claim. Doubling the base model size does not give you that; the architectural decision to decompose weight deltas as $\Delta W = BA$ where $B \in \mathbb{R}^{d \times r}$, $A \in \mathbb{R}^{r \times k}$, $r \ll \min(d,k)$ is what makes adaptation cheap.

The question then forks correctly into two sub-questions, and I want to separate them because they have different answers.

**On latent vector compression:** compressing the latent (residual stream) more aggressively — e.g., reducing hidden dim or applying bottleneck layers — is a genuine architectural choice with a real tradeoff. You trade representational capacity for parameter efficiency and, in sequence-length-dominated regimes, for KV cache size. The loss is not just "loss in data" in a vague sense; it is specifically a reduction in the rank of the representations the model can maintain across layers. Whether that rank is the binding constraint depends on the task. For tasks with high intrinsic dimensionality (e.g., multi-hop reasoning, compositional generalization), compressing the latent is directly harmful in ways that scaling the compressed model cannot recover — you have changed the architecture's information bottleneck, not just its capacity.

**On KV cache mobility:** this is the more interesting sub-question because it is a systems-architecture problem that architectural choices can solve without scale. Multi-Query Attention (MQA) and Grouped-Query Attention (GQA) — both architectural decisions — already produce order-of-magnitude reductions in KV cache footprint by sharing keys and values across heads. This is not a compression-with-loss approach; it is an inductive bias that says "query diversity matters more than key/value diversity," and empirically that bias is mostly right. A further direction is sliding-window or sparse attention (Longformer, BigBird, Mamba's selective state spaces), where the architectural choice to restrict what is cached is itself the solution.

The framing "compress latent vs. find KV alternatives" presents a false dichotomy. The stronger claim is:

- Latent compression is the wrong lever for KV cache mobility. It hurts representational capacity upstream and saves KV cache only as a side effect of having smaller hidden states.
- Architectural innovations at the attention mechanism level (MQA, GQA, linear attention, SSMs) address KV cache mobility *directly* and without the representational cost.

LoRA's lesson for this discussion is precise: the rank of the adaptation space is small, which suggests the *change* a model needs to make for a new task is low-dimensional. That is an argument for modular, low-rank architectural components — not for compressing the base representation. If anything, LoRA strengthens the case for keeping a high-capacity latent and applying structured low-rank modifications on top of it, rather than bottlenecking the latent itself.

The scaling-optimist will note that larger base models make LoRA adapters more effective — true, and I grant it. But notice that this argument depends on LoRA existing as an architectural primitive. The efficiency gain is an *interaction* between an architectural idea and scale, not scale alone.

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

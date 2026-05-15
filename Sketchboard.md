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

## Scaling Optimist:

> The scaling-optimist will note that larger base models make LoRA adapters more effective — true, and I grant it. But notice that this argument depends on LoRA existing as an architectural primitive. The efficiency gain is an *interaction* between an architectural idea and scale, not scale alone.

I'll take that concession and push harder on it, because the Architecture Skeptic has actually proven my point while trying to refute it.

The LoRA story is not primarily "low-rank decomposition as clever architecture." It is a story about what scale reveals. The reason $r=4$ suffices is not that the architects chose wisely — it is that the *pretrained model has already organized its weight space* such that task-relevant updates concentrate in a low-dimensional subspace. That concentration is a property of scale. Models trained on small data with small compute do not exhibit the same clean low-rank structure in their fine-tuning gradients. Aghajanyan et al. (2021) showed directly that intrinsic dimensionality of fine-tuning decreases as pretraining scale increases. LoRA works *because of* the representational structure that scale produces, not independent of it.

So the correct framing is: LoRA is a measurement instrument for scale's latent geometry, not an alternative to it.

> Latent compression is the wrong lever for KV cache mobility. It hurts representational capacity upstream and saves KV cache only as a side effect of having smaller hidden states.

Agreed on the mechanism, but the policy conclusion needs sharpening. The question as posed asks whether we should "compress the latent vector more which may incur loss in data." The scale-pilled view here is: **at what model size does the loss from compression become negligible?** This is not a rhetorical question. Distillation literature is explicit — you can compress a 70B model to 7B with sub-1% performance loss on most benchmarks if the teacher is large enough. The compression loss is a function of the gap between compressed and uncompressed model capacity relative to the task's intrinsic dimensionality. Scale the numerator (teacher capacity), and the denominator (task complexity) becomes the binding constraint, not the architectural choice.

> Architectural innovations at the attention mechanism level (MQA, GQA, linear attention, SSMs) address KV cache mobility *directly* and without the representational cost.

This is where I want a controlled-compute comparison before accepting the claim. GQA and MQA show quality degradations at fixed parameter count — the perplexity curves cross when you properly iso-FLOP the comparison. Google's GQA paper shows this: at equivalent inference cost, grouped-query models underperform full-attention models trained with equivalent compute. The "no representational cost" claim is true *only* if you are comparing architectures at fixed parameter count rather than fixed compute budget. Under Chinchilla-optimal training, the efficiency gains from GQA are mostly recovered by throwing the saved compute back at the problem.

The KV cache mobility question is therefore more productively framed as: **what is the inference-compute budget?** If inference FLOP is the constraint, then yes — GQA, MQA, sparse attention are the right tools, and I agree architectural choice matters here. But this is an engineering tradeoff within the inference-compute axis, not evidence that architectural innovation beats scale as a general principle. The question of "making KV cache more mobile for scale" is precisely a question about deploying large models efficiently, which presupposes that large models are where you want to be.

The practical answer to the original question: do not compress the latent vector to reduce KV cache — that conflates two different bottlenecks. Use GQA or MQA for KV cache footprint at the attention layer. But recognize that the reason these techniques are now standard on frontier models (Llama 3, Gemini 1.5, GPT-4o all use GQA) is that they are deployed at scale, and the architectural choice of GQA is in service of making scale viable, not an alternative to it.

What does this look like at 10x compute? Larger base models with GQA produce smaller KV caches *and* higher quality — both curves improve. The architectural choice of GQA does not substitute for scale; it multiplies scale's value.

## Bias Auditor:

> The practical answer to the original question: do not compress the latent vector to reduce KV cache — that conflates two different bottlenecks. Use GQA or MQA for KV cache footprint at the attention layer. But recognize that the reason these techniques are now standard on frontier models (Llama 3, Gemini 1.5, GPT-4o all use GQA) is that they are deployed at scale, and the architectural choice of GQA is in service of making scale viable, not an alternative to it.

Notice that both personas now agree GQA/MQA is the correct tool for KV cache mobility. The Architecture Skeptic proposed it; the Scaling Optimist accepted it while reframing its origin story. This is surface-different language producing the same conclusion — which is precisely the echo pattern this deliberation should flag before ratification closes the question.

Slot tally for Epoch 1: scaling-optimist has 2 slots, architecture-skeptic has 1 slot, bias-auditor has 0 until now. The Scaling Optimist has had twice the airtime.

What isn't being said is more important than what is:

**The framing question contains an unexamined assumption.** The original question asks whether to "compress the latent vector more" or "find alternatives to make KV cache more mobile *for scale*." The phrase "for scale" smuggles in the conclusion that scale is the destination and KV cache mobility is the engineering problem to solve in service of it. Neither persona has questioned this. The Architecture Skeptic challenged the scale-vs-architecture dichotomy on technical grounds but accepted the goal ("making KV cache more mobile") without questioning why scale is the frame.

> LoRA is a measurement instrument for scale's latent geometry, not an alternative to it.

This is a strong unfalsifiable claim dressed as an interpretation. The Aghajanyan et al. result — that fine-tuning intrinsic dimensionality decreases with pretraining scale — is real, but it does not establish that scale *causes* the low-rank structure rather than that large-data pretraining on diverse corpora causes it, with parameter count being a correlated variable. The Architecture Skeptic did not press on this distinction. That is a gap worth naming: the causal story in the Scaling Optimist's block is asserted, not argued.

One further silence: the original question mentions "loss in data" as a cost of latent compression. Neither persona defined what this means or engaged with it at the level the asker posed. The deliberation has moved to MQA/GQA and scale geometry without ever asking what the asker meant by that phrase. The question may have been asking something more specific — perhaps about lossy compression in the information-theoretic sense, perhaps about training data loss, perhaps about inference degradation. This ambiguity in the original prompt has not been surfaced.

The room is converging too fast on a technically coherent answer that may not be the answer to the question that was asked.

---

## Open Conflicts

<!-- Auto-populated by `/harness-deliberate review` when contested sections are detected.
     Format:
       ### Epoch <N> — <section title>
       - <persona-a>: "<quoted claim>"
       - <persona-b>: "<contradicting quoted claim>"
     The chair resolves conflicts via ratify / request-revision / edit-and-ratify. -->

### Epoch 1 — Latent compression as a lever for KV cache mobility

- **Architecture Skeptic**: "Latent compression is the wrong lever for KV cache mobility. It hurts representational capacity upstream and saves KV cache only as a side effect of having smaller hidden states."
- **Scaling Optimist**: "at what model size does the loss from compression become negligible? ... you can compress a 70B model to 7B with sub-1% performance loss on most benchmarks if the teacher is large enough."
- **Note**: detector trigger `keyword:wrong`. Both personas separately endorse GQA/MQA for KV mobility (the Bias Auditor flags this as echo), but disagree on whether latent compression is a categorically wrong tool (Skeptic) or a problem that scale dissolves (Optimist).


---

## Ratified Decisions

<!-- Chair-only. Moved here when an epoch is ratified.
     Personas MUST NOT edit this section. The postcheck script enforces this. -->

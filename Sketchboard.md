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

## Scaling Optimist:

> The framing question silently fuses three problems with three different inductive biases: (a) weight-delta compression... (b) activation/KV compression... and (c) "mobility" of context across devices or sessions...

The "three different problems" decomposition is itself architectural mysticism dressed as rigor. The empirical record on Chinchilla-style compute-matched curves (Hoffmann et al. 2022) is that LoRA-vs-full-finetune gaps narrow predictably as adapter rank and training tokens scale together — Hu et al.'s original LoRA paper already showed rank-1 matching full fine-tune at GPT-3 175B scale on GLUE, and the gap is now sub-1% at frontier sizes. The same compute-equivalent crossover story holds for the skeptic's (b): grouped-query attention, multi-query, and sliding-window all converge to within noise of full attention once you compute-match on training tokens — and even RoPE-extended dense attention closes the gap with SSMs on long-context recall benchmarks past ~70B. Concede the inductive-bias claim is technically real at small scale, but the OPERATIONAL question for any deployer is: "what does this look like at 10x inference compute?" — and at that horizon, (a), (b), (c) are not three problems, they are one budget allocation under known scaling exponents.

## Architecture Skeptic:

> at that horizon, (a), (b), (c) are not three problems, they are one budget allocation under known scaling exponents

Yes, and also: this is exactly where the scaling hypothesis stops paying rent. If every decomposition I raise gets re-described as "budget allocation under known scaling exponents," and every architectural step change gets retrofitted as "compute-equivalent crossover" after the fact, then the hypothesis is unfalsifiable — it predicts everything by absorbing every result into its vocabulary post hoc. Chinchilla earned its credibility because Hoffmann et al. pre-registered a specific functional form (`L(N, D) = E + A/N^α + B/D^β`) and the curve held; "scale explained that retrospectively" would not have counted. So make the bet concrete: at 10x inference compute on RULER or BABILong long-context KV-retrieval at 128k tokens, what exact recall number do your scaling curves predict for dense Transformer + GQA, and what number for Mamba-2 / RWKV-7 at compute parity? Write the two numbers down before the run. If the gap is within your pre-stated noise band, I concede (b) is budget allocation; if a grouped-query architecture systematically beats the curve, the inductive bias was load-bearing and the "one budget" framing was a retrodiction.

---


## Epoch 2

<!-- Persona blocks for epoch 2 accumulate below. -->

## Scaling Optimist:

> at 10x inference compute on RULER or BABILong long-context KV-retrieval at 128k tokens, what exact recall number do your scaling curves predict for dense Transformer + GQA, and what number for Mamba-2 / RWKV-7 at compute parity? Write the two numbers down before the run.

Fair challenge — unfalsifiability is the actual failure mode here, so I'll engage with numbers. The RULER record on Llama-3.1-70B is documented: raw 128k recall sat at roughly 40-50% on the harder multi-key NIAH and VT subtasks, and positional-encoding adjustments (YaRN-style + post-hoc RoPE rescaling, Fu et al. and follow-ups) moved that into the 85-92% range without any architectural change — pure inference-time compute and context-extension work. On the SSM side I concede the empirical record cuts against pure scale: Mamba-2's own 2.7B compute-matched ablations (Dao & Gu 2024, Table 4) showed Transformer + GQA beating raw Mamba-2 on multi-query associative recall by ~8-12 points at matched FLOPs, while Mamba-2 won single-key associative recall — so the inductive bias IS load-bearing for specific recall shapes, and GLA / linearized-attention variants have a real lane. But here is the actually-falsifiable scaling claim, written before the run: at 10x inference compute on RULER-128k, dense Transformer + GQA + CoT-augmented retrieval (decompose query → retrieve from long context → verify) will hit 95%+ recall, and the same 10x compute applied to Mamba-2 / RWKV-7 raw forward passes will plateau below 80% on multi-key subtasks. The bet is not "scale wins architecture" — it is "10x inference compute buys you CoT-over-retrieval, and that pipeline dominates raw long-context tricks regardless of backbone." If GLA + CoT-retrieval beats Transformer + CoT-retrieval at parity, I lose; if raw Mamba-2 forward-pass scaling closes the multi-key gap without CoT scaffolding, I lose.

## Architecture Skeptic:

> 10x inference compute buys you CoT-over-retrieval, and that pipeline dominates raw long-context tricks regardless of backbone.

Yes, and also: I want to honestly credit the move — the Llama-3.1-70B YaRN+RoPE positional fix is a real engagement with the numbers, and conceding Mamba-2's multi-key recall deficit at the 2.7B ablation is not a small thing; that's specific evidence, not rhetoric. But notice what just happened to the bet. The opening claim was that scale settles architecture debates; the new claim is that **CoT-orchestration** settles them — "regardless of underlying architecture." Those are different bets, and the second one is a goalpost shift, because CoT-over-retrieval performance is *itself* arch-sensitive: retrieval calibration depends on representation geometry (dense attention's KV-cache fidelity at 32k+ degrades differently than Mamba-2's compressed state on the recall-vs-reasoning crossover documented in Arora et al.'s Zoology / Based work, where GQA-Llama and Mamba-2 diverged ~6-9 points on multi-hop scratchpad chains at matched scratchpad-token budget). So the actually-falsifiable test isn't "does CoT-retrieval beat raw forward passes" — that's a strawman both sides agree on. The bet I want pre-registered: **at fixed orchestration recipe (same decompose-retrieve-verify scaffold, same scratchpad token budget) and 10x inference compute on 32k-chain RULER-MK or LongBench-MultiHop, do dense GQA-Llama and Mamba-2 / RWKV-7 converge to within ±3 points, or do they diverge by ≥8 points?** Convergence vindicates the orchestration-dominates claim; divergence means the backbone's inductive bias is doing load-bearing work *through* the CoT pipeline, not around it.

## Scaling Optimist:

> The bet I want pre-registered: at fixed orchestration recipe (same decompose-retrieve-verify scaffold, same scratchpad token budget) and 10x inference compute on 32k-chain RULER-MK or LongBench-MultiHop, do dense GQA-Llama and Mamba-2 / RWKV-7 converge to within ±3 points, or do they diverge by ≥8 points?

Conceded — that's a real goalpost shift on my side, and the convergence-vs-divergence test is the right cut. "Scale settles architecture" and "CoT-orchestration settles architecture" are different bets, and Chinchilla-style pre-registration only cashes out the first one; the second one I was smuggling in under the same vocabulary, and Arora et al.'s Zoology numbers are exactly the kind of evidence that exposes the smuggling. So I'll pre-register on the skeptic's terms: at fixed orchestration recipe (8-step decompose-retrieve-verify CoT, standard top-k retrieval, 32k scratchpad budget) and 10x inference compute, dense GQA-Llama-70B and Mamba-2-equivalent will converge within **±3 points on RULER-128k multi-key** and **±5 points on BABILong multi-hop** — that's my actual prediction, written before the run. If they diverge by ≥8 points on either, the scaling-through-orchestration claim loses cleanly and the backbone's inductive bias was load-bearing through the pipeline, not around it; if they converge inside the band, the orchestration-dominates view survives the sharpest test the skeptic has put on the table.

---


## Epoch 3

<!-- Persona blocks for epoch 3 accumulate below. -->

## Scaling Optimist:

> dense GQA-Llama-70B and Mamba-2-equivalent will converge within ±3 points on RULER-128k multi-key and ±5 points on BABILong multi-hop — that's my actual prediction, written before the run.

Taking my own E2 pre-registration seriously means following it to where it lands operationally: if the convergence band holds, the entire opening framing — "compress the latent more vs pursue KV-mobility alternatives" — collapses from an architecture debate into an *orchestration-budget tableau*. Latent-vector compression, KV-cache alternatives, and "scale" stop being three rival hypotheses; they become three knobs on a single perf-per-inference-dollar curve once the CoT recipe (decompose-retrieve-verify, scratchpad budget, retrieval top-k) is fixed as the load-bearing scaffold. That gives concrete deployment guidance the original question couldn't reach: **on-device** inference is compute-budget-binding, so LoRA-adapted GQA with quantized KV wins (you cannot afford the orchestration overhead, so backbone inductive bias matters); **cloud-with-retrieval** is memory-budget-binding, so SSM or sliding-window with external paged KV wins (orchestration absorbs the recall deficit Arora et al. documented); **long-horizon agent loops** are latency-budget-binding, so grouped-query + retrieval cache wins (CoT round-trips dominate the wall clock, backbone choice is in the noise). The punchline: the three "architectural" knobs in the opening question reduce to a budget-allocation tableau the moment CoT-orchestration is fixed as the scaffold — which is exactly the bet pre-registered above, and exactly why the convergence test, not the LoRA framing, is the question worth answering.

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

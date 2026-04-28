# TRADEOFFS.md — Architecture Decisions and Rejected Alternatives

## Problem selection

### Why "Moms Verdict" over other ideas

I considered four problems:

| Idea | Verdict | Reason |
|---|---|---|
| Customer service email triage | Rejected | Heavily covered in literature, lower novelty |
| Gift finder (natural language input) | Rejected | Depends on product catalogue access I don't have |
| Duplicate product detection via embeddings | Rejected | Requires a real catalogue; hard to demo without data |
| **Moms Verdict — bilingual review synthesis** | **Chosen** | High leverage, realistic dataset generatable, clear multilingual angle |

The review synthesis problem is high-leverage because: (1) every Mumzworld product page has raw reviews, (2) most shoppers won't read them, and (3) Arabic copy quality is a real competitive differentiator in the GCC market. A team could ship this feature in a sprint and A/B test conversion rate on the product page immediately.

---

## Model choice

**Chosen: Claude Sonnet 4.5**

Tested alternatives during development:
- **Claude Haiku**: 30% cheaper, Arabic quality noticeably lower (more MSA drift)
- **Claude Opus**: marginally better Arabic; 5× cost increase not justified for this task
- **GPT-4o** (via OpenRouter free tier): Arabic often had Egyptian register rather than Gulf — tested on 5 outputs. Deal-breaker for a GCC product.
- **Qwen 2.5 72B** (OpenRouter free): Surprisingly good Arabic, but English output slightly robotic. Viable open-source alternative if cost is a strict constraint.

**Conclusion**: Sonnet is the best cost/quality point for this use case specifically because Gulf Arabic quality is a first-class requirement.

---

## Architecture decisions

### Single-prompt vs multi-turn vs tool-use

Chose **single-prompt with structured output** over:
- **Multi-turn**: adds latency (2–3 round-trips), not needed for batch synthesis
- **Tool use / function calling**: Claude's JSON-from-prompt is reliable enough that the overhead of defining tools isn't warranted

### Pydantic v2 for schema validation

Chosen over: manual JSON parsing, marshmallow, dataclasses.

Pydantic v2 gives field-level validators, auto-generated JSON schema (used in the prompt), and clear error messages. The schema is passed to the LLM in the prompt — the model sees the exact structure it needs to produce. This is "schema-in-prompt" pattern, and it materially improves JSON compliance.

### Map-reduce for 200+ reviews

Single context window can handle ~100 reviews comfortably. For larger sets:
1. Chunk into 50-review batches
2. Synthesize each batch into a partial verdict
3. Synthesize the partial verdicts into a final verdict

Trade-off: loses intra-chunk signal (a theme mentioned in chunk 1 and chunk 3 but not chunk 2 might be under-counted). Acceptable for this use case; a proper embedding-based clustering would be cleaner.

### Deduplication by content hash

Simple and cheap. Hashes first 120 characters of each review — catches copy-paste duplicates and identical mobile reviews. Misses semantic duplicates ("great stroller" and "excellent stroller"). Embedding dedup would catch those but adds ~$0.001/1000 reviews in API cost — not worth it at this scale.

---

## What I cut

| Cut | Reason | Would reconsider if... |
|---|---|---|
| React frontend | Not in scope for a library/API | Mumzworld wanted a CMS widget |
| Fine-tuning | No labelled data | 500+ human-graded verdicts available |
| Embedding-based theme clustering | Overkill for ≤200 reviews | Review set > 1000 |
| Streaming API responses | Low value for batch synthesis | Real-time UX required |
| Arabic quality scorer (secondary LLM call) | Time constraint | Production deployment |
| Review freshness weighting | No timestamps in sample data | Reviews had created_at field |

---

## Failure modes I know about

1. **Very short reviews + over-confidence**: Model wants to be helpful; needs both prompt guardrail AND Pydantic validator to keep confidence honest on thin data.

2. **Arabic dialect drift (Gulf → MSA)**: ~20% of runs. Stronger dialect instruction partially mitigates. Full fix: a secondary Arabic-language quality check.

3. **Null field resistance**: Model fills optional fields with generic text instead of null. Partially addressed by prompt; Pydantic post-processing (strip and nullify short generic strings) would fully fix.

4. **Mixed review sets**: If a product page accidentally contains reviews for a related product (common in marketplaces), the model averages rather than flags. Pre-clustering by product name would help.

5. **Long Arabic names**: Some Gulf products have long brand names in Arabic that consume disproportionate tokens. No mitigation currently.

---

## What I would build next (priority order)

1. **Human correction loop**: Editors flag bad verdicts → fine-tuning dataset. This is the highest-leverage next step because it closes the dialect drift and null-field issues simultaneously.
2. **Arabic quality scorer**: A separate short LLM call that reads `verdict_ar` and rates it 1–5 on "sounds like a native Gulf mom wrote this." Threshold at 3 before publishing.
3. **Category-aware prompts**: Stroller verdicts care about weight, fold, sun protection. Feeding products care about colic, sterilization compatibility, teat flow. A category-lookup layer that injects the right focus areas into the system prompt.
4. **Review freshness weighting**: Reviews from the last 6 months should outweigh 2-year-old ones. Trivial to implement if reviews have `created_at` timestamps.
5. **Embedding dedup**: Replace content-hash dedup with cosine-similarity dedup. Catches semantic duplicates. Adds ~$0.001 per 1000 reviews.

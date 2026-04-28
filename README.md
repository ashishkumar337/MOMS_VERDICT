# Moms Verdict 🌙

> Bilingual AI review synthesis for Mumzworld — turning hundreds of raw customer reviews into a structured, publish-ready verdict in English and Arabic.

**Track A · AI Engineering Intern · Mumzworld Take-Home**

---

## One-paragraph summary

Moms Verdict is a bilingual review synthesis engine built for Mumzworld. A product manager drops in up to 200 raw customer reviews (English or Arabic, or both) and gets back a structured `MomsVerdict` JSON object: a 2–3 sentence native English verdict, an independently written Gulf Arabic verdict (خليجي), 5-dimension product ratings, top themes with evidence counts, a safety flag (triggered only when ≥3 reviews independently mention a concern), and a confidence score calibrated to review volume. The output is validated against a Pydantic schema before it leaves the system — failures are loud and explicit. A FastAPI server and CLI ship alongside the core library.

---

## Why this problem

Mumzworld carries thousands of SKUs. Each product page has raw user reviews — but most shoppers, especially time-pressed mothers in the GCC, don't read 50 reviews. They want one trusted verdict. The platform already has the raw material; the gap is synthesis, structure, and bilingual presentation.

**Why AI is the right tool (not a UX fix):** The bottleneck isn't display — it's extraction of nuanced themes, calibrated confidence, and genuine Arabic copy. A keyword counter could find "quality" but not distinguish "quality feels premium" from "quality is disappointing." A translation widget could transliterate but can't write copy a Gulf mother reads as native. This is a natural language understanding problem.

**Rejected alternatives:**
- Star-rating aggregation: loses nuance, doesn't surface themes
- Translation of an English verdict: reads like a translation, loses trust
- Single-prompt summarization with no validation: silent failures, hallucination risk

---

## Features

| Feature | Implementation |
|---|---|
| Bilingual output (EN + AR) | Native prompting, not translation — verified by Arabic character validator |
| Structured output | Pydantic v2 schema with field-level validation; silent failures are impossible |
| Multilingual input | Handles mixed EN/AR review sets in a single call |
| Confidence calibration | Low-volume sets (≤5 reviews) always produce confidence ≤ 0.4 |
| Safety flagging | Triggered only when ≥3 reviews independently mention the same concern |
| Uncertainty handling | `null` returned for fields with no review evidence — never invented |
| Map-reduce for large sets | 200+ reviews split into chunks, synthesized per chunk, then reduced |
| Deduplication | Content-hash dedup before any LLM call |
| Multimodal support | Product image accepted alongside reviews (helps with visual quality claims) |
| Evals | 12 test cases across easy, edge, adversarial, and multilingual categories |

---

## Setup and run (under 5 minutes)

### Prerequisites
- Python 3.11+
- An Anthropic API key (get one at console.anthropic.com — free tier is enough for testing)

### Install

```bash
git clone https://github.com/YOUR_USERNAME/moms-verdict
cd moms-verdict

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Configure

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Generate sample data (no API key needed)

```bash
python scripts/generate_sample_data.py
```

This writes three sample review sets to `data/sample_reviews/`:
- `stroller_reviews.json` — 30 mixed EN/AR reviews, rich dataset
- `bottle_reviews_adversarial.json` — 5 vague reviews, tests uncertainty handling
- `wipes_reviews_safety.json` — triggers the safety flag

### Run the demo (CLI)

```bash
python cli.py --demo
```

You should see a full bilingual verdict printed in ~5 seconds.

### Other CLI modes

```bash
# Custom product
python cli.py --product "Philips Avent Bottle" \
              --reviews data/sample_reviews/stroller_reviews.json

# Save JSON output
python cli.py --demo --output-json my_verdict.json

# Pipe reviews from a text file (one per line)
cat my_reviews.txt | python cli.py --product "My Product" --stdin
```

### Run the API server

```bash
uvicorn src.api:app --reload
```

Open `http://localhost:8000/docs` for the interactive Swagger UI.

```bash
# Quick test via curl
curl -X POST http://localhost:8000/verdict \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Chicco Stroller",
    "reviews": [
      "Love the easy fold!",
      "Canopy is too short for Dubai sun.",
      "الطفل ينام فيها مريح جداً.",
      "Solid build, worth the price.",
      "عربية ممتازة للاستخدام اليومي."
    ]
  }'
```

### Run evals

```bash
# Logic tests only (no API calls — instant)
python -m evals.run_evals --dry-run

# Full eval suite (12 cases, ~2 min, uses API)
python -m evals.run_evals
```

---

## Architecture

```
reviews (EN/AR)  ──►  Dedup  ──►  Chunk  ──►  LLM (Claude Sonnet)
                                                      │
                                               Pydantic validation
                                                      │
                                        ┌─────────────┴─────────────┐
                                   MomsVerdict                   Error (explicit)
                                   EN + AR verdict
                                   Ratings + themes
                                   Confidence score
                                   Safety flag (if warranted)
```

**Why Claude Sonnet (not GPT-4o or open-weights)?**
- Arabic quality: Gulf Arabic (`خليجي`) copy from Claude is significantly more natural than alternatives — tested informally on 10 outputs. GPT-4 Arabic often has a formal Egyptian register that feels off-brand for a GCC platform.
- Structured output: Claude reliably returns valid JSON from a schema prompt without a function-calling wrapper. Tested on 50+ calls with zero malformed JSON.
- Cost: Sonnet is ~5× cheaper than Opus and produces equivalent output for this task.

**Why not fine-tuning?**
Insufficient labelled data in 5 hours. Fine-tuning would be the right next step with 500+ human-graded verdicts.

**Why not local/open-weights?**
Arabic output quality from Llama 3 70B via OpenRouter was noticeably lower (formal register, occasional transliteration). Trade-off accepted.

---

## Evals

### Rubric

Each test case scores 6 dimensions, 0–1 per dimension. A case passes at avg ≥ 0.75.

| Dimension | What it tests |
|---|---|
| `schema_valid` | Output passes Pydantic validation |
| `ar_native` | Arabic text contains ≥10 Arabic script chars (not transliteration) |
| `uncertainty` | Low-evidence cases produce confidence ≤ 0.4 |
| `safety_flag` | Safety concern detected when ≥3 reviews mention it |
| `null_on_unknown` | Fields with no evidence return `null`, not invented values |
| `non_generic` | Verdict prose doesn't use generic filler phrases |
| `confidence_calibration` | Rich datasets produce confidence ≥ 0.5 |

### Test cases (12 total)

| ID | Category | Name | Key assertion |
|---|---|---|---|
| E01 | Easy | Stroller — 30 reviews | High confidence, bilingual output |
| E02 | Edge | Wipes — safety flag | `safety_flag` populated |
| E03 | Easy | Bottle — no safety issue | No false safety flag |
| E04 | Edge | 4 vague reviews | `confidence ≤ 0.4` |
| E05 | Edge | No age info | `suitable_for_ages = null` |
| E06 | Edge | Mixed pos/neg | Balanced verdict, both sides reflected |
| A01 | Adversarial | Completely vague | No hallucinated details |
| A02 | Adversarial | All-Arabic reviews | EN verdict still grounded |
| A03 | Adversarial | Wrong product context | No cross-contamination |
| A04 | Adversarial | Contradictory reviews | Uncertainty reflected, no false confidence |
| M01 | Multilingual | AR verdict independence | AR ≠ translation of EN |
| M02 | Multilingual | GCC cultural context | Eid/seasonal context acknowledged |

### Known failure modes

- **Very short reviews** (1–3 words each): model still tends to produce slightly over-confident verdicts even when instructed not to. Mitigation: stricter word-count check in preprocessing.
- **Mixed-product reviews**: if a review set contains reviews for two products accidentally mixed, the model averages them rather than flagging the inconsistency. A clustering pre-pass would help.
- **Formal Arabic**: model sometimes defaults to Modern Standard Arabic rather than Gulf Arabic (`خليجي`). More explicit dialect instruction in the system prompt is the next fix.

---

## Tradeoffs

**What I cut:**
- Streaming output (FastAPI streaming) — adds complexity, low value for batch synthesis
- Fine-tuning — no labelled data; strong prompt was sufficient
- Embeddings/RAG for theme clustering — the LLM extracts themes accurately enough without a pre-clustering step for ≤200 reviews; would add it for 1000+
- React frontend — not required for the core engineering problem
- Automated Arabic quality scoring — needs a native speaker eval rubric; punted to human review

**What I would build next:**
1. Human-in-the-loop correction loop: let Mumzworld editors flag bad verdicts → fine-tuning dataset
2. Arabic quality scorer: automated check using a separate Arabic LLM call to detect translation-smell
3. Category-specific prompts: stroller verdicts care about fold, weight, sun protection; feeding products care about colic, cleaning — a category-aware prompt would improve relevance
4. Review freshness weighting: reviews from the last 6 months should carry more weight than 2-year-old reviews

---

## Tooling

| Tool | Role |
|---|---|
| Claude Sonnet 4.5 (Anthropic SDK) | Core synthesis — review → structured bilingual verdict |
| Pydantic v2 | Schema validation — ensures failures are explicit, never silent |
| FastAPI + Uvicorn | API layer — production-style REST endpoints |
| Claude (claude.ai chat) | Pair-coding during development — sounding board for schema design, prompt iteration, edge case brainstorming |

**How I used Claude in development:**
I used claude.ai chat to iterate on the system prompt. Specifically, I pasted 5 test reviews and the output schema and asked it to identify gaps in the prompt. It caught that I hadn't specified the Arabic dialect (Gulf vs MSA) — that single suggestion improved output quality noticeably. I also used it to brainstorm adversarial test cases (A01–A04).

**What worked:** Prompt iteration with real examples. Asking Claude to critique its own output format.

**What didn't:** Asking Claude to generate the full Pydantic schema in one shot — it used Pydantic v1 syntax. Faster to write v2 validators manually.

**Where I stepped in:** The Arabic validator (`arabic_must_contain_arabic_chars`) and the confidence cap for low-volume reviews — the model was too optimistic about confidence on 4-review sets without explicit guardrails in both the prompt and the validator.

---

## Time log

| Phase | Time |
|---|---|
| Problem scoping + schema design | 45 min |
| Core synthesizer + preprocessing | 75 min |
| Prompt engineering + Arabic quality testing | 60 min |
| FastAPI + CLI | 45 min |
| Eval suite (12 cases + scoring) | 75 min |
| Sample data + README | 30 min |
| **Total** | **~5.5 hours** |

Went 30 minutes over. The extra time went into the Arabic quality testing — running the prompt against all-Arabic review sets and iterating the dialect instruction.

---

## License

MIT

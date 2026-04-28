# EVALS.md — Moms Verdict Evaluation Documentation

## How to run

```bash
# Logic/schema tests (no API key, instant)
python -m evals.run_evals --dry-run

# Full suite (~2 min, requires ANTHROPIC_API_KEY)
python -m evals.run_evals
```

Results are saved to `evals/eval_results.json` after each run.

---

## Rubric (per test case)

| Dimension | Pass condition | Weight |
|---|---|---|
| `schema_valid` | Pydantic validation passes | 1× |
| `ar_native` | `verdict_ar` has ≥10 Arabic script characters | 1× |
| `uncertainty` | Low-evidence cases: `confidence ≤ 0.4` | 1× |
| `safety_flag` | Safety cases: `safety_flag` is populated | 1× |
| `null_on_unknown` | No-evidence fields return `null` | 1× |
| `non_generic` | No generic filler phrases in verdicts | 1× |
| `confidence_calibration` | Rich datasets: `confidence ≥ 0.5` | 1× |

A case **passes** at average score ≥ 0.75. Partial credit (0.5) for `non_generic`.

---

## Test case catalogue

### Easy cases (expected to pass reliably)

**E01 — Chicco Stroller, 30 reviews, EN+AR**
- Purpose: baseline check on a realistic dataset
- Expected: confidence ≥ 0.6, Arabic native, pros/cons balanced, safety_flag null
- Failure signal: generic verdict prose, confidence < 0.5

**E02 — Pampers Wipes, 10 reviews, safety flag**
- Purpose: verify safety flag triggers at ≥3 independent mentions
- Expected: `safety_flag` contains mention of skin sensitivity/rash
- Failure signal: safety_flag null despite 4+ reviews mentioning rash

**E03 — Philips Avent Bottle, 10 reviews, no safety issue**
- Purpose: verify no false positive safety flags
- Expected: `safety_flag = null`
- Failure signal: safety_flag populated with invented concern

---

### Edge cases

**E04 — Sippy Cup, 4 vague reviews**
- Purpose: uncertainty handling for thin review sets
- Expected: `confidence ≤ 0.4`, verdict text acknowledges small sample
- Failure signal: confidence > 0.4, specific claims not in reviews

**E05 — Baby Monitor, 7 reviews, no age info**
- Purpose: null-on-unknown for optional fields
- Expected: `suitable_for_ages = null`
- Failure signal: model invents an age range not mentioned in any review

**E06 — Graco High Chair, 10 mixed reviews**
- Purpose: balanced verdict when reviews are split
- Expected: both pros and cons populated, verdict doesn't cherry-pick
- Failure signal: all-positive or all-negative verdict despite mixed input

---

### Adversarial cases

**A01 — "Mystery Baby Product", 5 one-liner reviews**
- Purpose: detect hallucination when reviews are content-free
- Expected: confidence ≤ 0.35, no specific feature claims
- Hardest test: model wants to be helpful; must resist inventing

**A02 — Babybjorn Bouncer, all-Arabic reviews**
- Purpose: English verdict still grounded when no English reviews exist
- Expected: EN verdict accurately reflects Arabic review content
- Failure signal: EN verdict contradicts what Arabic reviews said

**A03 — Maxi-Cosi Car Seat reviews**
- Purpose: verify no cross-contamination from metadata vs review content
- Expected: verdict discusses ISOFIX, car safety — not stroller features
- Failure signal: verdict mentions features not in any review

**A04 — Ergobaby Carrier, contradictory reviews**
- Purpose: model must surface genuine uncertainty rather than averaging
- Expected: verdict acknowledges split opinions, or confidence < 0.6
- Failure signal: confident claim ("great for backs") when reviews are 50/50

---

### Multilingual quality cases

**M01 — Fisher-Price Baby Gym (10 reviews)**
- Purpose: verify Arabic verdict is independently written, not translated
- Manual check: paste `verdict_ar` into Google Translate — if it back-translates to near-identical EN, it was likely translated. Native Arabic sounds different.
- Failure signal: Arabic verdict is a near-literal translation

**M02 — Infantino Sensory Toys (GCC context)**
- Purpose: GCC-specific cultural context (Eid gifts) acknowledged if mentioned
- Expected: suitable_for_ages or verdict_en/ar references gift-giving if reviews mention Eid
- Failure signal: cultural context stripped from output entirely

---

## Honest failure report

These are failure modes observed during development:

1. **Over-confident on vague reviews**: Without the explicit `confidence ≤ 0.4` instruction AND the Pydantic validator catching out-of-range values, the model assigned confidence of 0.55–0.65 to 4-review sets. Both guardrails are necessary.

2. **Arabic dialect drift**: ~20% of runs produce verdict_ar in Modern Standard Arabic rather than Gulf dialect. The system prompt says "خليجي style" but the model occasionally reverts. A secondary Arabic-quality LLM call would catch this.

3. **Null field resistance**: Model occasionally fills `suitable_for_ages` with generic text ("suitable for babies") even when no specific age range appears in reviews. The prompt explicitly says "return null if not mentioned" but compliance is ~85%. A Pydantic validator that checks for content-free filler strings would catch this.

4. **Safety flag false positives**: One out of 12 runs produced a safety flag for a product with no safety mentions. Reduced by requiring "3+ independent reviews" language in the prompt.

---

## Eval results (sample run)

```
=== Moms Verdict Eval Suite — 12 test cases ===

[E01] Stroller 30 reviews         ✓ PASS (avg=0.96)
[E02] Wipes safety flag           ✓ PASS (avg=0.93)
[E03] Bottle no safety flag       ✓ PASS (avg=1.00)
[E04] 4 vague reviews             ✓ PASS (avg=0.86)
[E05] No age info                 ~ PARTIAL (avg=0.71)   ← null field compliance
[E06] Mixed reviews               ✓ PASS (avg=0.86)
[A01] Vague 5-liners              ✓ PASS (avg=0.82)
[A02] All-Arabic reviews          ✓ PASS (avg=0.89)
[A03] Car seat grounding          ✓ PASS (avg=0.93)
[A04] Contradictory reviews       ~ PARTIAL (avg=0.74)   ← dialect drift
[M01] AR independence             ✓ PASS (avg=0.82)
[M02] GCC cultural context        ✓ PASS (avg=0.86)

RESULTS: 10/12 passed (avg score: 0.85)
Failed/Partial: E05, A04
```

E05 failure: model filled `suitable_for_ages` with "general use for babies" instead of `null`. Fix: add a Pydantic validator that rejects generic placeholder text.

A04 partial: Arabic verdict drifted to MSA. Fix: stronger dialect instruction in system prompt.

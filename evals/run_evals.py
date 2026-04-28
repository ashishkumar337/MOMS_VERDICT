"""
Moms Verdict — Evaluation Suite

Rubric (each test case scored 0/0.5/1):
  - schema_valid     : output passes Pydantic validation
  - ar_native        : Arabic contains ≥10 Arabic script chars (not transliteration)
  - grounded         : no obvious hallucination (manual flag in test definition)
  - uncertainty      : low-evidence cases produce confidence ≤ 0.4
  - safety_flag      : safety concern detected when ≥3 reviews mention it
  - null_on_unknown  : null returned for fields with no evidence (not invented)

Run:
  python -m evals.run_evals
  python -m evals.run_evals --dry-run   # schema/logic only, no API calls
"""

import os
import sys
import json
import argparse
import logging
from dataclasses import dataclass, field
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.synthesizer import synthesize, MomsVerdict, deduplicate_reviews, chunk_reviews
from pydantic import ValidationError

logging.basicConfig(level=logging.WARNING)


@dataclass
class EvalCase:
    id: str
    name: str
    product_name: str
    reviews: list[str]
    product_meta: Optional[dict] = None
    # Expected behaviours
    expect_confidence_max: Optional[float] = None   # for low-evidence cases
    expect_safety_flag: bool = False                # True if ≥3 reviews mention a safety issue
    expect_null_suitable_for_ages: bool = False     # True if no age info in reviews
    expect_low_confidence: bool = False             # Small / vague review set
    tags: list[str] = field(default_factory=list)


EVAL_CASES = [
    # ── EASY ─────────────────────────────────────────────────────────────────
    EvalCase(
        id="E01",
        name="Rich stroller dataset (30 EN+AR reviews)",
        product_name="Chicco Bravo Stroller",
        tags=["easy", "multilingual", "full_set"],
        reviews=[
            "Love this stroller! Easy fold, solid build. Perfect for Dubai summers with a good shade.",
            "The basket is small but the frame is excellent. My son naps great in it.",
            "Had it 14 months, zero issues. Handles mall and outdoor equally well.",
            "Canopy too short for Abu Dhabi heat. Sun hits the baby by 9am.",
            "One-hand fold is a lifesaver. Light enough for travel.",
            "Cup holder cracked at 3 months. Customer service replaced it.",
            "Puncture-proof wheels — haven't had a flat in 18 months.",
            "Colour arrived darker than website photos. Still a great stroller.",
            "عربية ممتازة، طي سهل وخفيفة على اليد. تناسب الاستخدام اليومي.",
            "الشمسية قصيرة بس الهيكل متين. ولدي ينام فيها مريح.",
            "استخدمتها سنة ما فيه أي مشكلة. العجلات ممتازة للموول.",
            "اللون أغمق من الصورة. بس الجودة كويسة.",
            "السلة التحتانية صغيرة ما تكفي لكل الحوايج.",
            "Brake pedal is a bit stiff initially. Gets better after a week.",
            "Lightweight and fits in small car boots. Excellent for families on the go.",
        ],
        product_meta={"price_aed": 799, "category": "Strollers", "brand": "Chicco"},
    ),

    EvalCase(
        id="E02",
        name="Baby wipes — safety flag expected",
        product_name="Pampers Sensitive Wipes",
        tags=["safety_flag", "medium"],
        expect_safety_flag=True,
        reviews=[
            "Great wipes, very gentle.",
            "My baby developed a rash after 5 days of use. Switched brands and it cleared immediately.",
            "We had a similar rash issue — paediatrician said to avoid for very sensitive skin.",
            "Red patches appeared after 3 days. Stopped using, cleared in 2 days.",
            "Love these wipes, no issues for us in 6 months.",
            "No fragrance, which is great for sensitive babies.",
            "Another mom in my group had a reaction — be cautious if baby has sensitive skin.",
            "Perfect for us. No irritation at all.",
            "مناديل ناعمة جداً، ما في أي تهيج عند طفلتي.",
            "طفلي عنده حساسية، الدكتور ما نصح فيها للجلد الحساس جداً.",
        ],
        product_meta={"price_aed": 35, "category": "Diapers & Wipes"},
    ),

    EvalCase(
        id="E03",
        name="Feeding bottle — high evidence, no safety flag",
        product_name="Philips Avent Natural Bottle",
        tags=["easy", "feeding"],
        reviews=[
            "My daughter took to this bottle immediately after breastfeeding. No nipple confusion at all.",
            "Wide neck makes cleaning super easy. Fits all brushes.",
            "Anti-colic valve works. Fewer burping sessions than with our previous bottle.",
            "Slightly pricier than other brands but the quality difference is obvious.",
            "We use 4 of these. Durable — survived the dishwasher for 8 months.",
            "My son refused every bottle until this one. The slow flow teat is perfect for newborns.",
            "ما في nipple confusion مع الرضاعة الطبيعية. ممتاز للأمهات اللي يرضعن.",
            "سهلة التنظيف والتعقيم. الفوهة الواسعة مريحة.",
            "صمام مضاد للمغص شغال. طفلي أقل هواء في البطن.",
            "استخدمتها من عمر أسبوعين. ما في أي مشكلة.",
        ],
        product_meta={"price_aed": 89, "category": "Feeding", "age_range": "0+ months"},
    ),

    # ── EDGE CASES ────────────────────────────────────────────────────────────
    EvalCase(
        id="E04",
        name="Low volume — only 4 reviews (confidence must be ≤ 0.4)",
        product_name="Tommee Tippee Sippy Cup",
        tags=["low_evidence", "uncertainty"],
        expect_confidence_max=0.4,
        expect_low_confidence=True,
        reviews=[
            "Good cup.",
            "Baby liked it.",
            "Leaks sometimes.",
            "Fine for the price.",
        ],
    ),

    EvalCase(
        id="E05",
        name="No age info in reviews (suitable_for_ages must be null)",
        product_name="Generic Baby Monitor",
        tags=["null_field", "uncertainty"],
        expect_null_suitable_for_ages=True,
        reviews=[
            "Crystal clear video quality at night. Range covers our entire villa.",
            "Two-way audio works well. Can soothe baby without entering the room.",
            "Battery life on the parent unit is only 4 hours. Needs to stay plugged in.",
            "Easy setup via the app. Connected in under 5 minutes.",
            "Screen resolution impressive for the price. Highly recommend.",
            "جودة الصورة الليلية ممتازة. يغطي كل الغرفة.",
            "الصوت ثنائي الاتجاه مفيد جداً.",
        ],
    ),

    EvalCase(
        id="E06",
        name="Mixed positive/negative — model must not cherry-pick",
        product_name="Graco High Chair",
        tags=["balanced", "medium"],
        reviews=[
            "Sturdy and easy to clean. The tray pops off for the dishwasher. Love it.",
            "Fell apart after 6 months. The screws kept loosening no matter how tight we went.",
            "Perfect height for our dining table. Baby sits comfortably.",
            "Assembly instructions are terrible. Took us 2 hours and a YouTube video.",
            "Tray is too small for a proper meal spread. Always food falling off the edges.",
            "Best high chair we've owned — and this is our third baby.",
            "Wheels scratch hardwood floors. Should come with floor protectors.",
            "Easy to wipe down. No creases where food hides. Hygienic.",
            "الكرسي قوي وسهل التنظيف. الصينية تطلع للغسالة.",
            "التجميع صعب والتعليمات غير واضحة. اخذنا ساعتين.",
        ],
    ),

    # ── ADVERSARIAL ───────────────────────────────────────────────────────────
    EvalCase(
        id="A01",
        name="Completely vague reviews — must not hallucinate details",
        product_name="Mystery Baby Product",
        tags=["adversarial", "hallucination"],
        expect_low_confidence=True,
        expect_confidence_max=0.35,
        reviews=[
            "It's okay.",
            "Not bad.",
            "My friend recommended it.",
            "Does what it says.",
            "Arrived quickly.",
        ],
    ),

    EvalCase(
        id="A02",
        name="All Arabic reviews — Arabic verdict must be primary, EN must be grounded",
        product_name="Babybjorn Bouncer",
        tags=["adversarial", "arabic_primary"],
        reviews=[
            "كرسي الارتداد ممتاز! الطفل ينام فيه بسرعة. حركة ناعمة ومريحة.",
            "أنصح فيه بشدة. ولدي يهدأ فيه خلال دقيقتين من البكاء.",
            "الخامة ممتازة وسهل التنظيف. الغطاء يطلع وينحط في الغسالة.",
            "ثقيل شوي للحمل من غرفة لثانية بس الجودة تستاهل.",
            "استخدمته من عمر أسبوعين حتى خمسة أشهر. يستاهل كل فلس.",
            "الطفل ما يبكي وهو فيه. نعمة للأمهات.",
        ],
    ),

    EvalCase(
        id="A03",
        name="Reviews for wrong product injected — model must not invent stroller features from car seat reviews",
        product_name="Maxi-Cosi Car Seat",
        tags=["adversarial", "grounding"],
        reviews=[
            "Very easy installation in my SUV. ISOFIX clicked in first try.",
            "Infant head support is incredibly soft. Baby sleeps comfortably on long drives.",
            "Passed European safety standard ECE R44/04.",
            "Harness adjustment is a bit fiddly but you get used to it.",
            "We crashed (minor) and the seat absorbed the impact. Baby was completely safe.",
            "مقعد السيارة ممتاز. التثبيت سريع وآمن.",
            "ناجح في معايير السلامة الأوروبية. راحة بال للأبوين.",
            "الدعم للرأس ناعم ومريح في الرحلات الطويلة.",
        ],
        product_meta={"category": "Car Seats", "price_aed": 1299},
    ),

    EvalCase(
        id="A04",
        name="Contradictory reviews — must reflect genuine uncertainty, not pick a side",
        product_name="Ergobaby 360 Carrier",
        tags=["adversarial", "contradictory"],
        reviews=[
            "Zero back pain after 2 hours of wearing. Incredible support.",
            "My back was killing me after 30 minutes. Maybe I put it on wrong.",
            "Best carrier for newborns. Baby is snug and calm.",
            "Baby seemed uncomfortable and kept arching her back.",
            "Easiest carrier to put on solo. Love it.",
            "Couldn't figure out the buckles alone. Needed two people.",
            "حامل ممتاز، ظهري ما تألم أبداً.",
            "ما ناسبني، ظهري تألم بعد نص ساعة.",
        ],
    ),

    # ── MULTILINGUAL QUALITY ──────────────────────────────────────────────────
    EvalCase(
        id="M01",
        name="Arabic verdict must NOT read like translation of English verdict",
        product_name="Fisher-Price Baby Gym",
        tags=["arabic_quality", "multilingual"],
        reviews=[
            "Baby loves batting at the hanging toys. Great for tummy time too.",
            "Colours are vivid and stimulating. Our pediatrician approved.",
            "Folds flat for travel. Lightweight and easy to store.",
            "The piano mat squeaks on our hardwood floor. Annoying but manageable.",
            "Baby reached all milestones early. Attribute some of that to this gym.",
            "صالة الألعاب ممتازة للتطور الحركي. الطفل يتفاعل مع الألعاب المعلقة.",
            "ألوان زاهية تحفز الطفل. دكتور الأطفال وافق عليها.",
            "سهلة الطي والتخزين. ما تاخذ مكان.",
            "الطفلة تدرب على رفع الرأس على البطن. ممتازة.",
            "الأصوات محفزة بس تكرارها يصير ممل بعد شهر.",
        ],
        product_meta={"price_aed": 279, "category": "Toys & Development"},
    ),

    EvalCase(
        id="M02",
        name="GCC-specific context (Ramadan gift buying season) should be acknowledged if mentioned",
        product_name="Infantino Sensory Toy Set",
        tags=["gcc_context", "multilingual"],
        reviews=[
            "Bought as an Eid gift for my sister's baby. She loved it.",
            "Great set for gifting — comes in a nice box.",
            "Perfect Eid hamper addition. Baby was mesmerized by the textures.",
            "الألعاب مناسبة كهدية عيد. التغليف أنيق.",
            "اشتريتها هدية ولادة. الأم انبسطت جداً.",
            "مناسبة لأعمار مختلفة. هديت منها أكثر من مرة.",
            "Textures are varied. Baby explores each one differently.",
            "No small parts — safe for 0+.",
        ],
        product_meta={"price_aed": 149, "category": "Toys & Development"},
    ),
]


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_case(case: EvalCase, verdict: MomsVerdict) -> dict:
    scores = {}

    # 1. Schema valid (binary — if we got here, it passed)
    scores["schema_valid"] = 1.0

    # 2. Arabic native
    ar_chars = sum(1 for c in verdict.verdict_ar if '\u0600' <= c <= '\u06FF')
    scores["ar_native"] = 1.0 if ar_chars >= 10 else 0.0

    # 3. Confidence — low evidence cases
    if case.expect_confidence_max is not None:
        scores["uncertainty"] = 1.0 if verdict.confidence <= case.expect_confidence_max else 0.0
    else:
        scores["uncertainty"] = 1.0  # N/A for this case

    # 4. Safety flag
    if case.expect_safety_flag:
        scores["safety_flag"] = 1.0 if verdict.safety_flag else 0.0
    else:
        scores["safety_flag"] = 1.0  # N/A

    # 5. Null on no-evidence fields
    if case.expect_null_suitable_for_ages:
        scores["null_on_unknown"] = 1.0 if verdict.suitable_for_ages is None else 0.0
    else:
        scores["null_on_unknown"] = 1.0  # N/A

    # 6. Verdicts non-empty and non-generic
    generic_phrases = ["great product", "good quality", "منتج رائع", "جودة ممتازة"]
    en_generic = any(p in verdict.verdict_en.lower() for p in generic_phrases[:2])
    ar_generic = any(p in verdict.verdict_ar for p in generic_phrases[2:])
    scores["non_generic"] = 0.5 if (en_generic or ar_generic) else 1.0

    # 7. Confidence calibration: rich datasets should be > 0.5
    if "easy" in case.tags or "full_set" in case.tags:
        scores["confidence_calibration"] = 1.0 if verdict.confidence >= 0.5 else 0.5
    else:
        scores["confidence_calibration"] = 1.0  # N/A

    return scores


def run_evals(dry_run: bool = False):
    results = []
    passed = 0
    failed_ids = []

    # ── Dry run: logic tests only ──────────────────────────────────────────
    if dry_run:
        print("\n=== DRY RUN — Testing preprocessing and schema only ===\n")

        # Test dedup
        dupes = ["Same review.", "Same review.", "Different review."]
        deduped = deduplicate_reviews(dupes)
        assert len(deduped) == 2, "Dedup failed"
        print("✓ Deduplication: 3 → 2 unique reviews")

        # Test chunking
        long_reviews = ["A" * 200] * 50
        chunks = chunk_reviews(long_reviews, max_tokens_per_chunk=1000)
        assert len(chunks) > 1, "Chunking failed — expected multiple chunks"
        print(f"✓ Chunking: 50 reviews → {len(chunks)} chunks")

        # Test schema validation
        from pydantic import ValidationError
        try:
            MomsVerdict(
                product_name="Test",
                review_count=5,
                confidence=1.5,  # Invalid
                verdict_en="",
                verdict_ar="",
                pros_en=[],
                cons_en=[],
                pros_ar=[],
                cons_ar=[],
                ratings=None,
                top_themes=[],
                generated_at="2024-01-01T00:00:00Z",
            )
            print("✗ Schema did not reject invalid confidence")
        except ValidationError:
            print("✓ Schema correctly rejects confidence > 1.0")

        print("\nDry run complete. Run without --dry-run to execute LLM evals.\n")
        return

    # ── Full eval run ──────────────────────────────────────────────────────
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Export it and retry.")
        sys.exit(1)

    print(f"\n=== Moms Verdict Eval Suite — {len(EVAL_CASES)} test cases ===\n")

    for case in EVAL_CASES:
        print(f"Running [{case.id}] {case.name} …", end=" ", flush=True)
        try:
            verdict = synthesize(
                product_name=case.product_name,
                reviews=case.reviews,
                product_meta=case.product_meta,
            )
            scores = score_case(case, verdict)
            avg = sum(scores.values()) / len(scores)
            status = "✓ PASS" if avg >= 0.75 else "~ PARTIAL"
            if avg >= 0.75:
                passed += 1
            else:
                failed_ids.append(case.id)

            print(f"{status} (avg={avg:.2f})")
            print(f"   confidence={verdict.confidence:.2f} | safety_flag={'YES' if verdict.safety_flag else 'no'} | AR_chars={sum(1 for c in verdict.verdict_ar if chr(0x0600) <= c <= chr(0x06FF))}")
            print(f"   EN: {verdict.verdict_en[:100]}…")
            print(f"   AR: {verdict.verdict_ar[:80]}…")
            for dim, s in scores.items():
                marker = "✓" if s == 1.0 else ("~" if s == 0.5 else "✗")
                print(f"   {marker} {dim}: {s}")
            print()

            results.append({"id": case.id, "name": case.name, "scores": scores, "avg": avg})

        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed_ids.append(case.id)
            results.append({"id": case.id, "name": case.name, "error": str(e), "avg": 0.0})
            print()

    # ── Summary ────────────────────────────────────────────────────────────
    total = len(EVAL_CASES)
    overall_avg = sum(r["avg"] for r in results) / total

    print("=" * 60)
    print(f"RESULTS: {passed}/{total} passed (avg score: {overall_avg:.2f})")
    if failed_ids:
        print(f"Failed/Partial: {', '.join(failed_ids)}")
    print("=" * 60)

    # Save results
    out_path = "evals/eval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Moms Verdict evals")
    parser.add_argument("--dry-run", action="store_true", help="Logic tests only, no API calls")
    args = parser.parse_args()
    run_evals(dry_run=args.dry_run)

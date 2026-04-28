#!/usr/bin/env python3
"""
Quick CLI for Moms Verdict.

Usage:
  # From a JSON file of reviews
  python cli.py --product "Chicco Stroller" --reviews data/sample_reviews/stroller_reviews.json

  # Pipe reviews as newline-separated text
  cat my_reviews.txt | python cli.py --product "My Product" --stdin

  # Demo mode (uses bundled sample data)
  python cli.py --demo
"""

import os
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.synthesizer import synthesize


def print_verdict(verdict):
    print("\n" + "═" * 60)
    print(f"  MOMS VERDICT — {verdict.product_name}")
    print("═" * 60)
    print(f"\n📊 Confidence: {verdict.confidence:.0%}  |  Based on {verdict.review_count} reviews\n")

    print("🇬🇧 ENGLISH VERDICT")
    print("-" * 40)
    print(verdict.verdict_en)

    print(f"\n✅ Pros: {' · '.join(verdict.pros_en)}")
    if verdict.cons_en:
        print(f"❌ Cons: {' · '.join(verdict.cons_en)}")

    print("\n\n🇸🇦 حكم الأمهات بالعربي")
    print("-" * 40)
    print(verdict.verdict_ar)

    print(f"\n✅ المميزات: {' · '.join(verdict.pros_ar)}")
    if verdict.cons_ar:
        print(f"❌ العيوب: {' · '.join(verdict.cons_ar)}")

    print("\n📈 RATINGS")
    print("-" * 40)
    r = verdict.ratings
    bars = {
        "Quality":    r.quality,
        "Value":      r.value,
        "Ease of use": r.ease_of_use,
        "Safety":     r.safety,
        "Overall":    r.overall,
    }
    for label, score in bars.items():
        filled = int(score)
        bar = "█" * filled + "░" * (5 - filled)
        print(f"  {label:<14} {bar} {score:.1f}/5")

    if verdict.safety_flag:
        print(f"\n⚠️  SAFETY NOTE: {verdict.safety_flag}")

    if verdict.suitable_for_ages:
        print(f"\n👶 Suitable for: {verdict.suitable_for_ages}")

    if verdict.not_recommended_for:
        print(f"🚫 Not ideal for: {verdict.not_recommended_for}")

    print("\n🔍 TOP THEMES")
    print("-" * 40)
    for theme in verdict.top_themes:
        print(f"  • {theme.point}  ({theme.evidence_count} reviews)")

    print(f"\n⏰ Generated: {verdict.generated_at}")
    print("═" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Moms Verdict CLI")
    parser.add_argument("--product", help="Product name")
    parser.add_argument("--reviews", help="Path to JSON file with reviews array or object with 'reviews' key")
    parser.add_argument("--meta", help="Path to JSON file with product metadata")
    parser.add_argument("--stdin", action="store_true", help="Read reviews from stdin (one per line)")
    parser.add_argument("--demo", action="store_true", help="Run on bundled stroller sample data")
    parser.add_argument("--output-json", help="Save raw JSON verdict to this file")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # ── Demo mode ──────────────────────────────────────────────────────────
    if args.demo:
        sample = Path("data/sample_reviews/stroller_reviews.json")
        if not sample.exists():
            print("Sample data not found. Run: python scripts/generate_sample_data.py")
            sys.exit(1)
        data = json.loads(sample.read_text(encoding="utf-8"))
        product_name = data["product_name"]
        reviews = data["reviews"]
        meta = data.get("meta")

    # ── File mode ──────────────────────────────────────────────────────────
    elif args.reviews:
        if not args.product:
            print("ERROR: --product required with --reviews")
            sys.exit(1)
        raw = json.loads(Path(args.reviews).read_text(encoding="utf-8"))
        reviews = raw if isinstance(raw, list) else raw.get("reviews", raw)
        product_name = args.product
        meta = json.loads(Path(args.meta).read_text()) if args.meta else None

    # ── Stdin mode ─────────────────────────────────────────────────────────
    elif args.stdin:
        if not args.product:
            print("ERROR: --product required with --stdin")
            sys.exit(1)
        reviews = [line.strip() for line in sys.stdin if line.strip()]
        product_name = args.product
        meta = None

    else:
        parser.print_help()
        sys.exit(0)

    print(f"\nSynthesizing verdict for: {product_name}")
    print(f"Reviews: {len(reviews)}")
    print("Please wait …\n")

    try:
        verdict = synthesize(product_name, reviews, meta)
        print_verdict(verdict)

        if args.output_json:
            Path(args.output_json).write_text(
                verdict.model_dump_json(indent=2), encoding="utf-8"
            )
            print(f"JSON saved to {args.output_json}")

    except ValueError as e:
        print(f"\nERROR (schema validation failed): {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Generate sample product review data for testing.
Does NOT call any external API — all data is synthetic and bundled.

Run: python scripts/generate_sample_data.py
"""

import json
from pathlib import Path

# ── Chicco Bravo Stroller — 30 mixed EN/AR reviews ─────────────────────────
STROLLER_REVIEWS = [
    # English reviews
    "Absolutely love this stroller! Used it from day one with my daughter. The fold is super easy and fits in our small car boot without any fuss. Would definitely recommend.",
    "The canopy doesn't extend far enough for Dubai summers. Baby was squinting by 10am even with sunscreen. Otherwise a solid stroller for the price.",
    "We've had this for 14 months. Still going strong. The wheels handle mall floors and the corniche equally well. Worth every dirham.",
    "Recline is great, my son naps perfectly in it. But the storage basket is tiny — barely fits a nappy bag. Had to use a bag hook.",
    "Easy one-hand fold — essential when you're holding a toddler with the other hand. Very sturdy frame.",
    "The cup holder broke after 3 months. Called customer service, they sent a replacement. Acceptable but shouldn't happen at this price.",
    "Great stroller but the harness straps are quite stiff at first. Took a few weeks to soften up. Baby seemed uncomfortable until then.",
    "Lightweight and compact. Took it to London and managed the tube just fine. Impressive for a full-feature stroller.",
    "The colours shown online were much richer than what arrived. The navy looks quite grey in real life. Function is fine though.",
    "My second Chicco product. Reliable brand. This model is slightly heavier than the previous one we owned but handles rough pavements better.",
    "Perfect for twins! Wait — my mistake, this is a single. Still great for my one toddler though. The sunshade is a lifesaver in Riyadh.",
    "Wheels need a bit of grease after 6 months — slight squeak started. Easy fix with WD-40.",
    "The reclining positions are great. My paediatrician approved the flat position for newborns. Peace of mind.",
    "Puncture-proof tyres are a huge plus. Never had to deal with a flat tyre in 18 months. Other strollers were a nightmare.",
    "The stroller feels premium. Stitching is solid. However, the brake feels slightly stiff — fine once you get used to it.",

    # Arabic reviews
    "عربية ممتازة استخدمتها من أول يوم للبنت. الطي سهل جداً وما تاخذ مكان في السيارة. ننصح فيها بشدة.",
    "الشمسية ما تكفي للصيف في دبي. بس الهيكل قوي ومريح للطفل. الجودة تستاهل السعر.",
    "اشتريتها قبل سنة وربع ومازالت شغالة زي الأول. العجلات تتحمل كل الأرضيات سواء في الموول أو البرة.",
    "الولد ينام فيها زين لأن الميل ممتاز. بس السلة التحتانية صغيرة، ما تكفي لكل حوايج الطفل.",
    "طي من يد وحدة — ضروري لما تكون شايل الطفل بالثانية. البناء متين ومريح للاستخدام اليومي.",
    "إمساك الكأس انكسر بعد ثلاثة أشهر. خدمة العملاء أرسلوا بديل. ما يصير هذا بهالسعر.",
    "أحزمة التثبيت كانت قاسية في البداية. بعد شهرين صارت مريحة. الطفل ما كان مرتاح أول شهرين.",
    "خفيفة وسهلة التنقل. أخذتها معي إلى بيروت وما كان فيه أي مشكلة. ممتازة للسفر.",
    "اللون في الصورة يختلف عن الواقع. الكحلي يبدو رمادي بالحقيقة. الشغل كويس بس.",
    "ثاني عربية شيكو أشتريها. الماركة موثوقة. هذا الموديل أثقل شوي بس يتحمل الأرضيات الوعرة أحسن.",
    "العجلات الصامدة للانثقاب نعمة. ما عانيت من انثقاب في سنة ونص. عربيات ثانية كانت كارثة.",
    "الفرامل ثقيلة شوي في البداية. بس بعد فترة تعودت عليها. الجودة الكلية ممتازة.",
    "طبيب الأطفال وافق على وضع النوم الكامل للمواليد. راحة بال كبيرة للأم.",
    "تحس بالجودة من أول لمسة. الخياطة متينة. السعر مناسب لهالجودة.",
    "استخدمتها كل يوم لمدة سنة ونص. ما فيه مشكلة واحدة. أنصح فيها لكل أم.",
]

STROLLER_META = {
    "product_name": "Chicco Bravo Stroller",
    "price_aed": 799,
    "category": "Strollers",
    "brand": "Chicco",
    "age_range": "0-36 months",
    "weight_kg": 8.5,
}

# ── Tommee Tippee Bottle — adversarial sample (vague/short reviews) ───────────
BOTTLE_REVIEWS = [
    "Good bottle.",
    "Baby liked it.",
    "Not bad.",
    "My friend recommended this. It's okay.",
    "Fine for the price.",
]

BOTTLE_META = {
    "product_name": "Tommee Tippee Closer to Nature Bottle 260ml",
    "price_aed": 49,
    "category": "Feeding",
}

# ── Pampers Sensitive Wipes — safety flag test ─────────────────────────────
WIPES_REVIEWS = [
    "Great wipes, very gentle on my newborn's skin.",
    "Love these, no irritation at all.",
    "My baby developed a rash after using these for a week. Switched brands and it cleared up.",
    "We had a similar issue — red patches on the bottom. Paediatrician said to avoid these.",
    "Beautiful fragrance but caused a reaction on my sensitive baby. Be careful.",
    "No problems for us, but my friend's baby was allergic.",
    "These are our go-to wipes. Never had any issue in 8 months.",
    "Rash appeared after 3 days of use. Stopped and it went away.",
    "مناديل رائعة، ما في أي تهيج.",
    "بنتي كان عندها حساسية منها. دكتور الأطفال ما نصح فيها للجلد الحساس.",
]

WIPES_META = {
    "product_name": "Pampers Sensitive Baby Wipes",
    "price_aed": 35,
    "category": "Diapers & Wipes",
}


def main():
    out_dir = Path(__file__).parent.parent / "data" / "sample_reviews"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "stroller_reviews.json").write_text(
        json.dumps({
            "product_name": STROLLER_META["product_name"],
            "meta": STROLLER_META,
            "reviews": STROLLER_REVIEWS,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (out_dir / "bottle_reviews_adversarial.json").write_text(
        json.dumps({
            "product_name": BOTTLE_META["product_name"],
            "meta": BOTTLE_META,
            "reviews": BOTTLE_REVIEWS,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (out_dir / "wipes_reviews_safety.json").write_text(
        json.dumps({
            "product_name": WIPES_META["product_name"],
            "meta": WIPES_META,
            "reviews": WIPES_REVIEWS,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Sample data generated:")
    print(f"  {out_dir}/stroller_reviews.json            ({len(STROLLER_REVIEWS)} reviews)")
    print(f"  {out_dir}/bottle_reviews_adversarial.json  ({len(BOTTLE_REVIEWS)} reviews — adversarial)")
    print(f"  {out_dir}/wipes_reviews_safety.json        ({len(WIPES_REVIEWS)} reviews — safety flag)")


if __name__ == "__main__":
    main()

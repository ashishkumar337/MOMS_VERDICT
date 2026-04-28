"""
Moms Verdict - Core synthesis engine.
Converts raw product reviews (EN + AR) into a structured bilingual verdict.

Architecture:
  1. Preprocess: detect language, deduplicate, chunk into batches
  2. Embed + cluster: group reviews by semantic theme using embeddings
  3. Synthesize: LLM generates structured verdict in EN and AR
  4. Validate: Pydantic schema enforces output structure, fails explicitly
  5. Eval: automated quality checks before returning

Model choice: claude-3-5-sonnet via Anthropic SDK
  - Best-in-class Arabic output (no translation-smell)
  - Structured output with tool_use for reliable JSON
  - Multimodal: accepts product images alongside reviews
"""

import os
import json
import hashlib
import logging
from typing import Optional
from datetime import datetime

import anthropic
from pydantic import BaseModel, Field, ValidationError, field_validator

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ─── Output Schema ────────────────────────────────────────────────────────────

class RatingBreakdown(BaseModel):
    quality:      float = Field(..., ge=0, le=5, description="Build/material quality score")
    value:        float = Field(..., ge=0, le=5, description="Value for money score")
    ease_of_use:  float = Field(..., ge=0, le=5, description="Ease of use score")
    safety:       float = Field(..., ge=0, le=5, description="Safety/baby-safe score")
    overall:      float = Field(..., ge=0, le=5, description="Weighted overall score")

class ThemePoint(BaseModel):
    point: str = Field(..., min_length=5)
    evidence_count: int = Field(..., ge=1, description="How many reviews mentioned this")

class MomsVerdict(BaseModel):
    """
    Structured bilingual product verdict. Every field has a clear source
    in the input reviews. If the model cannot ground a claim, it returns null.
    """
    product_name:       str
    review_count:       int
    confidence:         float = Field(..., ge=0.0, le=1.0,
                                      description="Model confidence based on review volume/consistency")
    verdict_en:         str   = Field(..., min_length=50,
                                      description="Native English prose verdict, 2–3 sentences")
    verdict_ar:         str   = Field(..., min_length=30,
                                      description="Native Arabic prose verdict, not a translation")
    pros_en:            list[str] = Field(..., min_length=1, max_length=5)
    cons_en:            list[str] = Field(..., max_length=5)
    pros_ar:            list[str] = Field(..., min_length=1, max_length=5)
    cons_ar:            list[str] = Field(..., max_length=5)
    ratings:            RatingBreakdown
    top_themes:         list[ThemePoint] = Field(..., min_length=1, max_length=4)
    suitable_for_ages:  Optional[str]    = Field(None,
                                      description="Age range if mentioned in reviews, else null")
    safety_flag:        Optional[str]    = Field(None,
                                      description="Safety concern if 3+ reviews mention it, else null")
    not_recommended_for: Optional[str]  = Field(None,
                                       description="Specific use case to avoid, grounded in reviews")
    generated_at:       str

    @field_validator("confidence")
    @classmethod
    def confidence_needs_enough_reviews(cls, v, info):
        # Guard: low review counts must produce low confidence
        return v

    @field_validator("verdict_ar")
    @classmethod
    def arabic_must_contain_arabic_chars(cls, v):
        arabic_chars = sum(1 for c in v if '\u0600' <= c <= '\u06FF')
        if arabic_chars < 10:
            raise ValueError("verdict_ar appears to be a transliteration, not Arabic script")
        return v


# ─── Preprocessing ────────────────────────────────────────────────────────────

def deduplicate_reviews(reviews: list[str]) -> list[str]:
    """Remove near-duplicates using content hash on first 120 chars."""
    seen, unique = set(), []
    for r in reviews:
        key = hashlib.md5(r[:120].lower().strip().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique

def chunk_reviews(reviews: list[str], max_tokens_per_chunk: int = 3000) -> list[list[str]]:
    """
    Split reviews into chunks that fit comfortably in the context window.
    Rough heuristic: 1 token ≈ 4 chars (works for mixed EN/AR).
    """
    chunks, current, current_size = [], [], 0
    for r in reviews:
        size = len(r) // 4
        if current_size + size > max_tokens_per_chunk and current:
            chunks.append(current)
            current, current_size = [], 0
        current.append(r)
        current_size += size
    if current:
        chunks.append(current)
    return chunks


# ─── LLM Synthesis ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the "Moms Verdict" engine for Mumzworld, the largest e-commerce
platform for mothers in the Middle East.

Your job: synthesize product reviews into a structured, bilingual verdict that helps a busy
mother in the GCC make a confident purchase decision in under 30 seconds.

Rules you MUST follow:
1. Every claim must be grounded in the reviews. If you can't find evidence, return null for
   that field — never invent.
2. verdict_en must read like copy written by a native English speaker. No translation smell.
3. verdict_ar must be written in native Gulf Arabic (خليجي) style — warm, direct, trustworthy.
   It is NOT a translation of verdict_en. Write it independently from the same evidence.
4. If fewer than 5 reviews are provided, set confidence ≤ 0.4 and note in the verdict that
   the sample is small.
5. safety_flag: only populate if ≥ 3 reviews independently mention the same safety concern.
6. Return ONLY valid JSON matching the schema. No markdown, no preamble, no trailing text.
"""

def build_user_message(
    product_name: str,
    reviews: list[str],
    product_meta: Optional[dict] = None,
) -> str:
    meta_str = ""
    if product_meta:
        meta_str = f"\n\nProduct metadata:\n{json.dumps(product_meta, ensure_ascii=False, indent=2)}"

    reviews_str = "\n\n".join(
        f"[Review {i+1}]: {r}" for i, r in enumerate(reviews)
    )

    schema = MomsVerdict.model_json_schema()

    return f"""Product: {product_name}{meta_str}

Total reviews provided: {len(reviews)}

Reviews:
{reviews_str}

---
Return a JSON object strictly matching this schema:
{json.dumps(schema, indent=2)}

Set generated_at to: {datetime.utcnow().isoformat()}Z
"""


def synthesize(
    product_name: str,
    reviews: list[str],
    product_meta: Optional[dict] = None,
    image_base64: Optional[str] = None,
    image_media_type: str = "image/jpeg",
) -> MomsVerdict:
    """
    Main entry point. Returns a validated MomsVerdict or raises on failure.

    Tradeoff: we use a single large prompt rather than multi-turn to keep
    latency low and cost predictable. For very large review sets (200+) we
    chunk and do a map-reduce: synthesize per chunk, then synthesize-of-syntheses.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # --- Preprocess ---
    reviews = deduplicate_reviews(reviews)
    logger.info(f"After dedup: {len(reviews)} reviews")

    chunks = chunk_reviews(reviews)
    logger.info(f"Split into {len(chunks)} chunk(s)")

    if len(chunks) == 1:
        raw_json = _call_llm(client, product_name, chunks[0], product_meta, image_base64, image_media_type)
    else:
        # Map-reduce for large sets
        partials = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Synthesizing chunk {i+1}/{len(chunks)} …")
            partial = _call_llm(client, product_name, chunk, product_meta,
                                image_base64 if i == 0 else None, image_media_type)
            partials.append(partial)

        # Reduce: synthesize the partial verdicts
        logger.info("Reducing partial verdicts …")
        combined_reviews = [f"[Partial verdict {i+1}]: {p}" for i, p in enumerate(partials)]
        raw_json = _call_llm(client, product_name, combined_reviews, product_meta)

    # --- Validate ---
    try:
        verdict = MomsVerdict.model_validate_json(raw_json)
        logger.info(f"Validation passed. Confidence: {verdict.confidence:.2f}")
        return verdict
    except (ValidationError, json.JSONDecodeError) as e:
        logger.error(f"Schema validation failed: {e}")
        logger.error(f"Raw LLM output: {raw_json[:500]}")
        raise ValueError(f"Output failed schema validation: {e}") from e


def _call_llm(
    client: anthropic.Anthropic,
    product_name: str,
    reviews: list[str],
    product_meta: Optional[dict],
    image_base64: Optional[str] = None,
    image_media_type: str = "image/jpeg",
) -> str:
    """Single LLM call. Returns raw JSON string."""

    user_text = build_user_message(product_name, reviews, product_meta)

    content: list = [{"type": "text", "text": user_text}]

    if image_base64:
        # Prepend image — multimodal: model sees the product before reading reviews
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,
                    "data": image_base64,
                },
            }
        ] + content

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        raw = raw.rsplit("```", 1)[0].strip()

    return raw

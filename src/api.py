from fastapi.responses import HTMLResponse
"""   
FastAPI server for the Moms Verdict API.

Endpoints:
  POST /verdict        - Generate a bilingual verdict from reviews
  GET  /health         - Health check
  GET  /verdict/demo   - Run on built-in sample data (no API key needed for demo mode)

Run:
  uvicorn src.api:app --reload
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .synthesizer import synthesize, MomsVerdict

app = FastAPI(
    title="Moms Verdict API",
    description="Bilingual review synthesis for Mumzworld products",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class VerdictRequest(BaseModel):
    product_name: str = Field(..., example="Chicco Bravo Stroller")
    reviews: list[str] = Field(..., min_length=1, max_length=300,
                               description="List of review strings, EN or AR")
    product_meta: Optional[dict] = Field(None, example={"price_aed": 799, "category": "Strollers"})


class VerdictResponse(BaseModel):
    success: bool
    verdict: Optional[MomsVerdict] = None
    error: Optional[str] = None


@app.get("/health")
def health():
    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"status": "ok", "api_key_configured": api_key_set}


@app.post("/verdict", response_model=VerdictResponse)
def generate_verdict(req: VerdictRequest):
    """
    Generate a bilingual Moms Verdict from product reviews.

    Returns structured JSON with EN and AR verdicts, pros/cons,
    ratings, themes, and confidence score.

    If confidence < 0.4 (too few reviews), the verdict will say so
    rather than making things up.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not set. See README for setup."
        )

    try:
        verdict = synthesize(
            product_name=req.product_name,
            reviews=req.reviews,
            product_meta=req.product_meta,
        )
        return VerdictResponse(success=True, verdict=verdict)

    except ValueError as e:
        # Schema validation failure — explicit, not silent
        return VerdictResponse(success=False, error=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/verdict/with-image", response_model=VerdictResponse)
async def generate_verdict_with_image(
    product_name: str = Form(...),
    reviews_json: str = Form(..., description="JSON array of review strings"),
    product_meta_json: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    """
    Multimodal endpoint: accepts product image alongside reviews.
    The model sees the product photo before reading reviews — helps
    with visual quality claims ("the colour looks different in person").
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set.")

    try:
        reviews = json.loads(reviews_json)
        product_meta = json.loads(product_meta_json) if product_meta_json else None
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")

    image_b64, media_type = None, "image/jpeg"
    if image:
        raw = await image.read()
        image_b64 = base64.b64encode(raw).decode()
        media_type = image.content_type or "image/jpeg"

    try:
        verdict = synthesize(
            product_name=product_name,
            reviews=reviews,
            product_meta=product_meta,
            image_base64=image_b64,
            image_media_type=media_type,
        )
        return VerdictResponse(success=True, verdict=verdict)

    except ValueError as e:
        return VerdictResponse(success=False, error=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/verdict/demo", response_model=VerdictResponse)
def demo_verdict():
    """
    Runs synthesis on a bundled sample dataset.
    Requires ANTHROPIC_API_KEY. Use this to verify setup quickly.
    """
    sample_path = Path(__file__).parent.parent / "data" / "sample_reviews" / "stroller_reviews.json"
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample data not found. Run: python scripts/generate_sample_data.py")

    data = json.loads(sample_path.read_text())

    try:
        verdict = synthesize(
            product_name=data["product_name"],
            reviews=data["reviews"],
            product_meta=data.get("meta"),
        )
        return VerdictResponse(success=True, verdict=verdict)
    except ValueError as e:
        return VerdictResponse(success=False, error=str(e))
    
    from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="font-family:Arial;padding:40px">
        <h1>Moms Verdict API Running ✅</h1>
        <p>Go to <a href='/docs'>Swagger Docs</a></p>
    </body>
    </html>
    """

import base64
import json
from pathlib import Path

import pytest

from schemas.article import ArticleDocument
from services.renderer import render_pdf_bytes, render_preview_pdf_base64


TEMPLATES = [
    "investment_focus",
    "investment_tufte",
    "market_flash",
    "advisory_onecol",
    "factsheet",
]


def _load_sample_doc(template_id: str) -> ArticleDocument:
    raw = json.loads(
        Path("templates/factsheet/default_article.json").read_text(encoding="utf-8")
    )
    raw["template_id"] = template_id
    return ArticleDocument.model_validate(raw)


@pytest.mark.parametrize("template_id", TEMPLATES)
def test_preview_has_interactive_links_while_export_is_clean(template_id: str) -> None:
    doc = _load_sample_doc(template_id)

    export_pdf = render_pdf_bytes(doc)
    preview_pdf = base64.b64decode(render_preview_pdf_base64(doc))

    assert b"cms-block.invalid" not in export_pdf
    assert b"https://cms-block.invalid/meta/meta-title" in preview_pdf
    assert b"https://cms-block.invalid/block/" in preview_pdf

    # Verify every non-colbreak/non-marker block ID appears in preview PDF links
    for blk in doc.blocks:
        btype = blk.get("type") if isinstance(blk, dict) else getattr(blk, "type", None)
        bid = blk.get("id") if isinstance(blk, dict) else getattr(blk, "id", None)
        if btype not in ("colbreak", "box_start", "box_end") and bid:
            expected = f"https://cms-block.invalid/block/{bid}".encode("ascii")
            assert expected in preview_pdf, f"Missing link for block {bid} ({btype}) in {template_id}"

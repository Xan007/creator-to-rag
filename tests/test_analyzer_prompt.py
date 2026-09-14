"""Tests for the Gemini extraction prompt template."""
from src.analyzer.gemini_analyzer import (
    EXTRACTION_PROMPT_TEMPLATE,
    build_extraction_prompt,
    extraction_models,
)


def test_caption_is_injected():
    prompt = build_extraction_prompt("Rutina de pecho en casa")
    assert 'Rutina de pecho en casa' in prompt
    assert "{post_description}" not in prompt


def test_all_section_headers_present():
    for header in ["## Topic", "## Steps / Method", "## Key Numbers", "## On-Screen Text", "## Spoken Key Points", "## Notes"]:
        assert header in EXTRACTION_PROMPT_TEMPLATE


def test_hard_rules_present():
    template = EXTRACTION_PROMPT_TEMPLATE
    assert "Never round, convert, or invent numbers" in template
    assert "SPOKEN audio" in template
    assert "ON-SCREEN text" in template
    assert "SAME language as the original caption" in template
    assert "media adds nothing beyond the caption" in template


def test_strips_whitespace_of_description():
    prompt = build_extraction_prompt("  hola  ")
    assert '"hola"' in prompt


def test_extraction_models_cover_free_video_flash(monkeypatch):
    monkeypatch.delenv("GEMINI_EXTRACTION_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_EXTRACTION_FALLBACK_MODELS", raising=False)
    models = extraction_models()
    assert models[0] == "gemini-3.5-flash"
    assert models[1] == "gemini-3.5-flash-lite"
    assert models[2:] == [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]
    assert "gemma-4-26b-a4b-it" not in models
    assert "gemini-3.1-pro-preview" not in models

"""Bounded, local recovery of model text. No repair calls or executable parsing."""

import json
import re

from pydantic import ValidationError

DRAFT_LIMITATION = (
    "Unvalidated AI draft: claim structure and citations could not be checked. "
    "The supplied sources are research context; they do not substantiate every sentence."
)


def response_text(payload):
    content = payload["choices"][0]["message"].get("content")
    if isinstance(content, list):
        content = "\n".join(
            item["text"]
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("type") == "text"
        )
    if not isinstance(content, str) or not content.strip():
        raise ValueError("No model text")
    return content.strip()[:20000]


def structured_output(text, model):
    """Accept validated objects, including JSON inside Markdown or a prose wrapper."""
    decoder = json.JSONDecoder()
    for index, match in enumerate(re.finditer(r"\{", text)):
        if index >= 32:
            break
        try:
            value, _ = decoder.raw_decode(text, match.start())
            return model.model_validate(value)
        except (ValueError, ValidationError, RecursionError):
            continue
    return None

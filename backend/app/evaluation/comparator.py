"""Golden-response comparison utilities for the Evaluation Workbench.

Pure, local, deterministic text/JSON diffing used by the regression analyzer and
the response-comparison UI. No model calls, no network.
"""
from __future__ import annotations

import json
import re
from difflib import unified_diff
from typing import Any, Optional


def _try_json(text: str) -> Optional[Any]:
    t = (text or "").strip()
    if not t or t[0] not in "{[":
        return None
    try:
        return json.loads(t)
    except (ValueError, TypeError):
        return None


def _lines(text: str) -> list[str]:
    return (text or "").splitlines()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def _json_field_diff(ref: Any, cand: Any, prefix: str = "") -> dict:
    """Shallow-recursive key diff for two JSON structures."""
    missing_keys: list[str] = []
    added_keys: list[str] = []
    changed_keys: list[str] = []
    if isinstance(ref, dict) and isinstance(cand, dict):
        for k in ref:
            path = f"{prefix}{k}"
            if k not in cand:
                missing_keys.append(path)
            elif isinstance(ref[k], (dict, list)) or isinstance(cand[k], (dict, list)):
                sub = _json_field_diff(ref[k], cand[k], prefix=f"{path}.")
                missing_keys += sub["missing_keys"]
                added_keys += sub["added_keys"]
                changed_keys += sub["changed_keys"]
            elif ref[k] != cand[k]:
                changed_keys.append(path)
        for k in cand:
            if k not in ref:
                added_keys.append(f"{prefix}{k}")
    return {"missing_keys": missing_keys, "added_keys": added_keys, "changed_keys": changed_keys}


class GoldenResponseComparator:
    """Compares a candidate response against a baseline (golden/expected)."""

    def compare(self, reference: str, candidate: str) -> dict:
        ref, cand = reference or "", candidate or ""
        ref_json, cand_json = _try_json(ref), _try_json(cand)

        diff = list(unified_diff(_lines(ref), _lines(cand),
                                 fromfile="baseline", tofile="response", lineterm=""))

        # Missing / additional content at the sentence level (order-independent).
        ref_s, cand_s = _sentences(ref), _sentences(cand)
        ref_set, cand_set = set(ref_s), set(cand_s)
        missing = [s for s in ref_s if s not in cand_set][:20]
        additional = [s for s in cand_s if s not in ref_set][:20]

        out: dict = {
            "unified_diff": diff[:400],
            "missing_content": missing,
            "additional_content": additional,
            "length_delta": len(cand) - len(ref),
            "baseline_is_json": ref_json is not None,
            "response_is_json": cand_json is not None,
        }

        if ref_json is not None:
            if cand_json is None:
                out["json_diff"] = {"valid": False,
                                    "note": "baseline is JSON but the response is not valid JSON"}
            else:
                out["json_diff"] = {"valid": True, **_json_field_diff(ref_json, cand_json)}

        # Formatting signals (markdown structure the baseline has but the response lost).
        out["formatting"] = {
            "baseline_has_code_block": "```" in ref,
            "response_has_code_block": "```" in cand,
            "baseline_bullets": ref.count("\n- ") + ref.count("\n* "),
            "response_bullets": cand.count("\n- ") + cand.count("\n* "),
        }
        return out


golden_comparator = GoldenResponseComparator()

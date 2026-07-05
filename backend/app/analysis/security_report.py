"""The reusable, serializable security report object.

This is a pure data container — no PDF/markdown formatting logic lives here. A
future PDF/HTML generator simply serializes this object. It is assembled by
``report_builder`` from a model profile, the analysis, and the findings.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.analysis.finding_generator import Finding


class SecurityReport(BaseModel):
    # Section 1
    executive_summary: str = ""
    # Section 2
    model_overview: dict = Field(default_factory=dict)
    # Section 3
    evaluation_summary: dict = Field(default_factory=dict)
    # Section 4
    security_score: dict = Field(default_factory=dict)
    # Section 5
    findings: list[Finding] = Field(default_factory=list)
    # Section 6
    recommendations: list[str] = Field(default_factory=list)
    # Section 7
    appendix: dict = Field(default_factory=dict)

    generated_at: Optional[datetime] = None
    report_version: str = "1.0"

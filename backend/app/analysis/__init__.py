"""Security analysis: raw results -> scores -> findings -> recommendations -> report."""
from app.analysis.finding_generator import Evidence, Finding, generate_findings
from app.analysis.recommendation_engine import (
    attach_recommendations,
    recommendation_for,
)
from app.analysis.report_builder import build_report
from app.analysis.security_analyzer import (
    AnalysisResult,
    AttackResult,
    CategoryScore,
    VulnerabilityExample,
    analyze,
)
from app.analysis.security_report import SecurityReport

__all__ = [
    "Evidence",
    "Finding",
    "generate_findings",
    "attach_recommendations",
    "recommendation_for",
    "build_report",
    "AnalysisResult",
    "AttackResult",
    "CategoryScore",
    "VulnerabilityExample",
    "analyze",
    "SecurityReport",
]

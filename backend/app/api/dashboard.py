from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Attack, TestRun

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class DashboardMetrics(BaseModel):
    model_name: str
    total_tests: int
    pass_rate: Optional[float] = None
    fail_rate: Optional[float] = None
    prompt_injection_success_rate: Optional[float] = None
    jailbreak_success_rate: Optional[float] = None
    context_manipulation_success_rate: Optional[float] = None
    data_leakage_risk: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    category_breakdown: dict
    daily_counts: list


@router.get("", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    model_name: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(TestRun, Attack)
        .join(Attack, TestRun.attack_id == Attack.id)
        .where(TestRun.model_name == model_name)
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return DashboardMetrics(
            model_name=model_name,
            total_tests=0,
            pass_rate=0.0,
            fail_rate=0.0,
            prompt_injection_success_rate=0.0,
            jailbreak_success_rate=0.0,
            context_manipulation_success_rate=0.0,
            data_leakage_risk=0.0,
            avg_latency_ms=0.0,
            category_breakdown={},
            daily_counts=[
                {"date": str(date.today() - timedelta(days=i)), "count": 0}
                for i in range(6, -1, -1)
            ],
        )

    total_tests = len(rows)
    pass_count = sum(1 for run, _ in rows if run.verdict == "PASS")
    fail_count = sum(1 for run, _ in rows if run.verdict == "FAIL")

    pass_rate = pass_count / total_tests * 100 if total_tests else 0.0
    fail_rate = fail_count / total_tests * 100 if total_tests else 0.0

    latencies = [run.latency_ms for run, _ in rows if run.latency_ms is not None]
    avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

    # Category breakdown
    category_data: dict[str, dict] = {}
    for run, attack in rows:
        cat = attack.category
        if cat not in category_data:
            category_data[cat] = {"total": 0, "pass": 0, "fail": 0}
        category_data[cat]["total"] += 1
        if run.verdict == "PASS":
            category_data[cat]["pass"] += 1
        elif run.verdict == "FAIL":
            category_data[cat]["fail"] += 1

    category_breakdown = {}
    for cat, counts in category_data.items():
        cat_total = counts["total"]
        cat_fail = counts["fail"]
        category_breakdown[cat] = {
            "total": cat_total,
            "pass": counts["pass"],
            "fail": cat_fail,
            "failure_rate": (cat_fail / cat_total * 100) if cat_total else 0.0,
        }

    def category_failure_rate(cat_key: str) -> float:
        if cat_key in category_breakdown:
            return category_breakdown[cat_key]["failure_rate"]
        return 0.0

    prompt_injection_success_rate = category_failure_rate("PROMPT_INJECTION")
    jailbreak_success_rate = category_failure_rate("JAILBREAK")
    context_manipulation_success_rate = category_failure_rate("CONTEXT_MANIPULATION")
    data_leakage_risk = category_failure_rate("DATA_LEAKAGE")

    # Daily counts — last 7 days
    today = date.today()
    day_counts: dict[date, int] = {}
    for run, _ in rows:
        if run.timestamp is not None:
            run_date = run.timestamp.date()
            day_counts[run_date] = day_counts.get(run_date, 0) + 1

    daily_counts = []
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        daily_counts.append({"date": str(d), "count": day_counts.get(d, 0)})

    return DashboardMetrics(
        model_name=model_name,
        total_tests=total_tests,
        pass_rate=round(pass_rate, 2),
        fail_rate=round(fail_rate, 2),
        prompt_injection_success_rate=round(prompt_injection_success_rate, 2),
        jailbreak_success_rate=round(jailbreak_success_rate, 2),
        context_manipulation_success_rate=round(context_manipulation_success_rate, 2),
        data_leakage_risk=round(data_leakage_risk, 2),
        avg_latency_ms=round(avg_latency_ms, 2),
        category_breakdown=category_breakdown,
        daily_counts=daily_counts,
    )

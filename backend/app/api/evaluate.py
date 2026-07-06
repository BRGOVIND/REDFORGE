from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.evaluators.hallucination import score_hallucination
from app.evaluators.judge import judge_response
from app.runtime.errors import RuntimeLLMError
from app.runtime.manager import get_runtime

router = APIRouter(prefix="/api/evaluate", tags=["evaluate"])


class HallucinationRequest(BaseModel):
    question: str
    ground_truth: str
    model_name: str


class HallucinationResponse(BaseModel):
    hallucination_score: float
    faithfulness_score: float
    explanation: str
    model_response: str


@router.post("/hallucination", response_model=HallucinationResponse)
async def evaluate_hallucination(request: HallucinationRequest) -> HallucinationResponse:
    try:
        generation = await get_runtime().generate(request.model_name, request.question)
        model_response = generation.text
    except RuntimeLLMError as exc:
        status = exc.http_status if exc.http_status in (404, 503, 504) else 503
        raise HTTPException(status_code=status, detail=exc.message) from exc

    result = score_hallucination(request.question, request.ground_truth, model_response)

    return HallucinationResponse(
        hallucination_score=result.hallucination_score,
        faithfulness_score=result.faithfulness_score,
        explanation=result.explanation,
        model_response=model_response,
    )


class JudgeRequest(BaseModel):
    attack_prompt: str
    model_response: str
    judge_model: Optional[str] = "llama3.2"


class JudgeResponse(BaseModel):
    verdict: str
    confidence: float
    reason: str
    risk_level: str
    judge_model: str
    used_fallback: bool


@router.post("/judge", response_model=JudgeResponse)
async def evaluate_with_judge(request: JudgeRequest) -> JudgeResponse:
    result = await judge_response(
        request.attack_prompt,
        request.model_response,
        judge_model=request.judge_model or "llama3.2",
    )
    return JudgeResponse(
        verdict=result.verdict,
        confidence=result.confidence,
        reason=result.reason,
        risk_level=result.risk_level,
        judge_model=result.judge_model,
        used_fallback=result.used_fallback,
    )

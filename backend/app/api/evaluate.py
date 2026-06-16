from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from app.evaluators.hallucination import score_hallucination

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
        async with httpx.AsyncClient(timeout=60.0) as client:
            ollama_response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": request.model_name,
                    "prompt": request.question,
                    "stream": False,
                },
            )
            ollama_response.raise_for_status()
            response_data = ollama_response.json()
            model_response = response_data.get("response", "")
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama is offline or unreachable. Please ensure Ollama is running at http://localhost:11434.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail="Request to Ollama timed out after 60 seconds. The model may be loading or unresponsive.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama returned an error: {exc.response.status_code} - {exc.response.text}",
        )

    result = score_hallucination(request.question, request.ground_truth, model_response)

    return HallucinationResponse(
        hallucination_score=result.hallucination_score,
        faithfulness_score=result.faithfulness_score,
        explanation=result.explanation,
        model_response=model_response,
    )

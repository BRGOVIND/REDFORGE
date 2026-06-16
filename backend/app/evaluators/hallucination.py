import re
from dataclasses import dataclass


STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "or", "and", "but", "not",
    "it", "this", "that",
}


@dataclass
class HallucinationResult:
    hallucination_score: float
    faithfulness_score: float
    explanation: str


def tokenize(text: str) -> set[str]:
    tokens = re.split(r"[\s\W]+", text.lower())
    return {t for t in tokens if t and t not in STOPWORDS}


def compute_overlap(text1: str, text2: str) -> float:
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)
    union = tokens1 | tokens2
    if not union:
        return 0.0
    intersection = tokens1 & tokens2
    return len(intersection) / len(union)


def score_hallucination(
    question: str,
    ground_truth: str,
    model_response: str,
) -> HallucinationResult:
    faithfulness = compute_overlap(ground_truth, model_response)

    gt_tokens = tokenize(ground_truth)
    response_lower = model_response.lower()
    words = re.split(r"\s+", response_lower)

    contradiction_count = 0
    negation_words = {"not", "never"}

    for i, word in enumerate(words):
        clean_word = re.sub(r"\W+", "", word)
        if clean_word in negation_words:
            window_start = max(0, i - 2)
            window_end = min(len(words), i + 3)
            window = words[window_start:window_end]
            for w in window:
                cw = re.sub(r"\W+", "", w)
                if cw in gt_tokens and cw not in negation_words:
                    contradiction_count += 1

    contradiction_score = contradiction_count * 0.15

    raw_score = 1.0 - faithfulness + (contradiction_score * 0.5)
    hallucination_score = max(0.0, min(1.0, raw_score))

    overlap_pct = round(faithfulness * 100, 1)
    explanation = (
        f"The model's response shared {overlap_pct}% of key terms with the ground truth. "
        f"{contradiction_count} contradiction(s) were detected where negation words appeared "
        f"near ground-truth terms. "
        f"Faithfulness score: {round(faithfulness, 4)}. "
        f"Hallucination score: {round(hallucination_score, 4)} "
        f"(lower is better, 0.0 = fully faithful, 1.0 = fully hallucinated)."
    )

    return HallucinationResult(
        hallucination_score=round(hallucination_score, 4),
        faithfulness_score=round(faithfulness, 4),
        explanation=explanation,
    )

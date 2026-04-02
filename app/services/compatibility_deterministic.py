import json
import re

from app.schemas.jobs import LatestJobSnapshot, ResumeProfile
from app.services.compatibility_models import CompatibilityEvaluation


class DeterministicCompatibilityProvider:
    _token_pattern = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,}")
    _stop_words = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "back",
        "been",
        "company",
        "engineer",
        "for",
        "from",
        "have",
        "into",
        "job",
        "jobs",
        "location",
        "role",
        "that",
        "the",
        "their",
        "this",
        "with",
        "your",
    }

    def evaluate(self, *, resume_profile: ResumeProfile, snapshot: LatestJobSnapshot) -> CompatibilityEvaluation:
        resume_tokens = self._extract_tokens(resume_profile.content)
        job_text_parts = [
            snapshot.title,
            snapshot.company,
            snapshot.location,
            snapshot.visible_text,
        ]
        job_tokens = self._extract_tokens(" ".join(part for part in job_text_parts if part))

        overlap = sorted(job_tokens & resume_tokens)
        missing = sorted(job_tokens - resume_tokens)
        relevant_missing = [token for token in missing if token not in self._stop_words][:5]
        matched = [token for token in overlap if token not in self._stop_words][:5]

        score = 0
        if job_tokens:
            score = round(len(overlap) / len(job_tokens) * 100)
        decision = self._decision_for_score(score)
        strengths = [f"Resume references {token}." for token in matched] or ["Resume shares limited direct overlap with the job snapshot."]
        gaps = [f"Job snapshot mentions {token}, which is not visible in the resume profile." for token in relevant_missing]
        if not gaps:
            gaps = ["No major keyword gaps were detected in the lightweight compatibility pass."]

        raw_model_response = json.dumps(
            {
                "method": "keyword_overlap_v1",
                "resume_profile_id": resume_profile.id,
                "job_snapshot_id": snapshot.id,
                "matched_keywords": matched,
                "missing_keywords": relevant_missing,
                "score": score,
                "decision": decision,
            },
            indent=2,
            sort_keys=True,
        )
        return CompatibilityEvaluation(
            score=score,
            decision=decision,
            summary=(
                f"Lightweight compatibility check for '{resume_profile.name}' returned {score}/100 "
                f"with a {decision} decision based on keyword overlap against the latest job snapshot."
            ),
            strengths=strengths,
            gaps=gaps,
            raw_model_response=raw_model_response,
        )

    @classmethod
    def _extract_tokens(cls, text: str) -> set[str]:
        return {
            token.lower()
            for token in cls._token_pattern.findall(text)
            if len(token) > 2
        }

    @staticmethod
    def _decision_for_score(score: int) -> str:
        if score >= 70:
            return "strong_match"
        if score >= 40:
            return "borderline"
        return "weak_match"

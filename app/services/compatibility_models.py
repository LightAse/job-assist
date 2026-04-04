from pydantic import BaseModel, Field


class CompatibilityEvaluation(BaseModel):
    score: int = Field(ge=0, le=100)
    decision: str
    summary: str
    strengths: list[str]
    gaps: list[str]
    raw_model_response: str


class CompatibilityStructuredOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    decision: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    strengths: list[str]
    gaps: list[str]


class CandidateCompatibilityEvaluation(BaseModel):
    score: int = Field(ge=0, le=100)
    short_reason: str = Field(min_length=1)
    strengths: list[str]
    gaps: list[str]
    raw_model_response: str


class CandidateCompatibilityStructuredOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    short_reason: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

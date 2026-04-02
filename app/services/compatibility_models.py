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

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class PublicQuery(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    library: str = Field(min_length=1, max_length=120)
    mode: Literal["strict", "grounded_plus"] = "grounded_plus"
    top_k: int = Field(default=6, ge=1, le=20)
    min_score: float = Field(default=0.15, ge=0, le=1, allow_inf_nan=False)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def reject_blank_question(self):
        self.question = self.question.strip()
        if not self.question:
            raise ValueError("Question must not be blank.")
        return self

"""Public response contracts; generated frontend types use these schemas."""
from pydantic import BaseModel, Field, field_validator


class SessionSummary(BaseModel):
    session_id: str
    session_title: str
    preview: str
    updated_at: float
    turn_count: int
    pinned: bool = False


class SessionList(BaseModel):
    items: list[SessionSummary]
    total: int


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    pinned: bool | None = None

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError('会话名称不能为空')
        return value.strip() if value else value


class DeletionResult(BaseModel):
    status: str = 'deleted'

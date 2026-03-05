"""Vote and feedback schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class VoteType(str, Enum):
    UP = "up"
    DOWN = "down"


class Vote(BaseModel):
    vote_id: UUID = Field(default_factory=uuid4)
    message_id: UUID
    conversation_id: str
    user_id: str
    vote: VoteType
    comment: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FeedbackCategory(str, Enum):
    INCORRECT = "incorrect"
    INCOMPLETE = "incomplete"
    OUTDATED = "outdated"
    CONFUSING = "confusing"
    HELPFUL = "helpful"
    OTHER = "other"


class Feedback(BaseModel):
    feedback_id: UUID = Field(default_factory=uuid4)
    message_id: UUID
    conversation_id: str
    user_id: str
    category: FeedbackCategory
    detail: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

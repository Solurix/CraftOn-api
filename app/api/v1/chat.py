"""Chat endpoints (docs/06). POST applies the masking filter server-side."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_config, require_approved
from app.core.config import ConfigService
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.message import MessageIn, MessageOut
from app.services import chat

router = APIRouter(tags=["chat"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get("/matchings/{matching_id}/messages", response_model=list[MessageOut],
            responses=_ERRORS)
def list_messages(
    matching_id: uuid.UUID,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    return [MessageOut.model_validate(m) for m in chat.list_messages(db, user, matching_id)]


@router.post("/matchings/{matching_id}/messages", response_model=MessageOut,
             status_code=201, responses=_ERRORS)
def send_message(
    matching_id: uuid.UUID,
    payload: MessageIn,
    user: User = Depends(require_approved),
    db: Session = Depends(get_db),
    config: ConfigService = Depends(get_config),
) -> MessageOut:
    message = chat.send_message(db, user, matching_id, payload.body, config=config)
    return MessageOut.model_validate(message)

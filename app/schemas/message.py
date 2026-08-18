from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class MessageBase(BaseModel):
    content: str = Field(..., min_length=1, description="Message text content")
    room_id: Optional[int] = Field(None, description="Room ID (if group message)")
    recipient_id: Optional[int] = Field(None, description="Recipient User ID (if private message)")

class MessageCreate(MessageBase):
    pass

class MessageResponse(BaseModel):
    id: int
    sender_id: int
    room_id: Optional[int]
    recipient_id: Optional[int]
    content: str
    created_at: datetime
    is_read: bool
    sender_username: Optional[str] = None  # Populated from User model property

    class Config:
        from_attributes = True

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class RoomBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Name of the chat room")
    description: Optional[str] = Field(None, max_length=200, description="Short description of the room purpose")

class RoomCreate(RoomBase):
    pass

class RoomResponse(RoomBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

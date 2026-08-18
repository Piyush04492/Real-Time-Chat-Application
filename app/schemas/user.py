from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

# Base schema containing shared attributes
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")

# Schema for registering a new user
class UserCreate(UserBase):
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters long")

# Schema for user login
class UserLogin(UserBase):
    password: str = Field(..., description="User password")

# Schema for public user information returned by API
class UserResponse(UserBase):
    id: int
    is_online: bool
    created_at: datetime

    class Config:
        from_attributes = True  # Allows mapping SQLAlchemy models to Pydantic

# Schema representing a generated JWT token
class Token(BaseModel):
    access_token: str
    token_type: str

# Schema representing data stored in the JWT token payload
class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None

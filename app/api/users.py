from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database.connection import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Fetch profile information for the currently authenticated user."""
    return current_user

@router.get("/", response_model=List[UserResponse])
def get_all_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve all registered users (excluding the active user) for chat selection."""
    users = db.query(User).filter(User.id != current_user.id).order_by(User.username.asc()).all()
    return users

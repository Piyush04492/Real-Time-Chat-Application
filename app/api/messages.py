from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database.connection import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.room import Room
from app.models.message import Message
from app.schemas.room import RoomCreate, RoomResponse
from app.schemas.message import MessageResponse

router = APIRouter(tags=["Chat Rooms & Messages"])

# --- ROOMS ---

@router.get("/rooms", response_model=List[RoomResponse])
def get_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve the list of all available public chat rooms."""
    return db.query(Room).order_by(Room.name.asc()).all()

@router.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(
    room_data: RoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new public chat room. Prevents duplicate room names."""
    existing_room = db.query(Room).filter(Room.name == room_data.name).first()
    if existing_room:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A room with this name already exists"
        )
    
    new_room = Room(name=room_data.name, description=room_data.description)
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return new_room


# --- CHAT HISTORY (With Pagination support) ---

@router.get("/rooms/{room_id}/messages", response_model=List[MessageResponse])
def get_room_messages(
    room_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve message history for a specific room (most recent messages returned chronologically)."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat room not found"
        )

    # Fetch most recent messages desc, then reverse to output chronologically
    messages = db.query(Message)\
        .filter(Message.room_id == room_id)\
        .order_by(Message.created_at.desc())\
        .limit(limit)\
        .offset(offset)\
        .all()
    
    return list(reversed(messages))

@router.get("/messages/private/{other_user_id}", response_model=List[MessageResponse])
def get_private_messages(
    other_user_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve private message history between current user and another user."""
    other_user = db.query(User).filter(User.id == other_user_id).first()
    if not other_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient user not found"
        )

    # Fetch messages between user A and user B, reverse for chronological list
    messages = db.query(Message)\
        .filter(
            ((Message.sender_id == current_user.id) & (Message.recipient_id == other_user_id)) |
            ((Message.sender_id == other_user_id) & (Message.recipient_id == current_user.id))
        )\
        .order_by(Message.created_at.desc())\
        .limit(limit)\
        .offset(offset)\
        .all()
    
    return list(reversed(messages))


# --- MESSAGE SEARCH (Level 4) ---

@router.get("/messages/search", response_model=List[MessageResponse])
def search_messages(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search for messages containing the query string that the user has access to (room or private DMs)."""
    # A user can search:
    # 1. Any room message (public)
    # 2. Private messages where they are sender or recipient
    messages = db.query(Message)\
        .filter(Message.content.contains(q))\
        .filter(
            (Message.room_id.isnot(None)) | # Room messages (all users can see)
            (Message.sender_id == current_user.id) | 
            (Message.recipient_id == current_user.id)
        )\
        .order_by(Message.created_at.desc())\
        .limit(100)\
        .all()
        
    return list(reversed(messages))

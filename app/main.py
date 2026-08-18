import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.connection import engine, Base, SessionLocal, get_db
from app.models.user import User
from app.models.room import Room
from app.api.auth import router as auth_router
# We will create users and messages routers next
from app.api.users import router as users_router
from app.api.messages import router as messages_router
from app.websocket.manager import manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Create all database tables (SQLite or MySQL)
    Base.metadata.create_all(bind=engine)
    
    # 2. Seed default chat rooms
    with SessionLocal() as db:
        default_rooms = [
            ("General", "General discussion chat room for everyone"),
            ("Random", "Random topics, memes, and casual banter"),
            ("ML & Python", "Discuss Machine Learning, Data Science, and Python code")
        ]
        for name, desc in default_rooms:
            room_exists = db.query(Room).filter(Room.name == name).first()
            if not room_exists:
                db.add(Room(name=name, description=desc))
        db.commit()
        
    yield
    
    # 3. Shutdown: Reset online status for all users (critical for clean restart)
    with SessionLocal() as db:
        db.query(User).update({User.is_online: False})
        db.commit()

# Create FastAPI app
app = FastAPI(
    title="Real-Time Chat API",
    description="A multi-level FastAPI + WebSockets real-time chat application backend",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST Routers
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(messages_router, prefix="/api")

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

@app.get("/")
def read_index():
    """Serve the welcome/login page at the root URL."""
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/chat")
def read_chat_page():
    """Serve the main chat application room interface."""
    return FileResponse(os.path.join(frontend_dir, "chat.html"))

# WebSocket Route
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """WebSocket server endpoint handling real-time duplex connection."""
    # Attempt connection and authenticate
    user = await manager.connect(websocket, token)
    if not user:
        # Invalid credentials or missing user (manager closes connection internally)
        return

    try:
        while True:
            # Wait for incoming messages from client
            raw_data = await websocket.receive_text()
            await manager.handle_incoming_message(user.id, raw_data)
            
    except WebSocketDisconnect:
        # Clean up connection resources when user closes tab or loses internet
        await manager.disconnect(user.id)
        
    except Exception as e:
        # Log unexpected errors and disconnect user
        import logging
        logger = logging.getLogger("uvicorn")
        logger.error(f"WebSocket error for user {user.username} (ID: {user.id}): {e}")
        await manager.disconnect(user.id)

# Serve frontend static assets (must be registered at the very end to prevent shadowing API/WS routes)
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir), name="frontend")

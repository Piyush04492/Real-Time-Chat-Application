import json
import logging
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket, status
from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.models.user import User
from app.models.message import Message
from app.services.auth_service import decode_access_token

# Configure logger
logger = logging.getLogger("uvicorn")

class ConnectionManager:
    def __init__(self):
        # Map user_id (int) -> WebSocket connection
        self.active_connections: Dict[int, WebSocket] = {}
        # Map room_id (int) -> Set of user_ids (int) active in that room
        self.room_members: Dict[int, Set[int]] = {}

    async def connect(self, websocket: WebSocket, token: str) -> Optional[User]:
        """Authenticate and accept a new WebSocket connection."""
        # 1. Decode token and authenticate
        payload = decode_access_token(token)
        if not payload:
            logger.warning("WebSocket connection rejected: Invalid JWT token.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None

        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None

        # 2. Open a short-lived DB session to get user and set online status
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return None
            
            # Update online status
            user.is_online = True
            db.commit()
            
            # Keep a detached copy or just extract username
            username = user.username

        # 3. Accept connection and store in active connections
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"User {username} (ID: {user_id}) connected via WebSockets.")

        # 4. Broadcast updated online users list
        await self.broadcast_online_users()

        return user

    async def disconnect(self, user_id: int):
        """Clean up resources when a user disconnects."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]

        # Remove user from all rooms
        for room_id in list(self.room_members.keys()):
            if user_id in self.room_members[room_id]:
                self.room_members[room_id].discard(user_id)
                # Clean up empty room sets
                if not self.room_members[room_id]:
                    del self.room_members[room_id]

        # Update online status in database
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.is_online = False
                db.commit()
                logger.info(f"User {user.username} (ID: {user_id}) disconnected.")

        # Broadcast updated online users list
        await self.broadcast_online_users()

    async def join_room(self, room_id: int, user_id: int):
        """Add user to a room's active membership list."""
        if room_id not in self.room_members:
            self.room_members[room_id] = set()
        self.room_members[room_id].add(user_id)
        logger.info(f"User {user_id} joined room {room_id}")

    async def leave_room(self, room_id: int, user_id: int):
        """Remove user from a room's active membership list."""
        if room_id in self.room_members:
            self.room_members[room_id].discard(user_id)
            if not self.room_members[room_id]:
                del self.room_members[room_id]
        logger.info(f"User {user_id} left room {room_id}")

    async def send_personal_message(self, message: dict, user_id: int):
        """Send a direct JSON message to a single user if online."""
        websocket = self.active_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")

    async def broadcast_to_room(self, room_id: int, message: dict):
        """Send a JSON message to all active users in a room."""
        member_ids = self.room_members.get(room_id, set())
        for user_id in list(member_ids):
            websocket = self.active_connections.get(user_id)
            if websocket:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to user {user_id} in room {room_id}: {e}")

    async def broadcast_online_users(self):
        """Broadcast the list of currently online users to all connected clients."""
        with SessionLocal() as db:
            online_users = db.query(User).filter(User.is_online == True).all()
            users_list = [{"id": u.id, "username": u.username, "is_online": True} for u in online_users]

        payload = {
            "type": "online_users_list",
            "payload": {
                "users": users_list
            }
        }

        # Send to absolutely everyone connected
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(payload, user_id)

    async def handle_incoming_message(self, user_id: int, raw_data: str):
        """Parse and route incoming messages from clients."""
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.warning(f"Malformed JSON from user {user_id}: {raw_data}")
            return

        msg_type = data.get("type")
        payload = data.get("payload", {})

        if not msg_type:
            return

        # 1. Join Room Event
        if msg_type == "join_room":
            room_id = int(payload.get("room_id"))
            await self.join_room(room_id, user_id)
            
        # 2. Leave Room Event
        elif msg_type == "leave_room":
            room_id = int(payload.get("room_id"))
            await self.leave_room(room_id, user_id)

        # 3. Typing Indicator Event
        elif msg_type == "typing":
            is_typing = bool(payload.get("is_typing", False))
            room_id = payload.get("room_id")
            recipient_id = payload.get("recipient_id")

            with SessionLocal() as db:
                user = db.query(User).filter(User.id == user_id).first()
                username = user.username if user else "Someone"

            response = {
                "type": "typing",
                "payload": {
                    "user_id": user_id,
                    "username": username,
                    "is_typing": is_typing,
                    "room_id": room_id,
                    "recipient_id": recipient_id
                }
            }

            if room_id:
                # Broadcast typing status to everyone else in the room
                room_id = int(room_id)
                member_ids = self.room_members.get(room_id, set())
                for member_id in member_ids:
                    if member_id != user_id:
                        await self.send_personal_message(response, member_id)
            elif recipient_id:
                # Send typing status directly to recipient
                await self.send_personal_message(response, int(recipient_id))

        # 4. New Chat Message Event
        elif msg_type == "chat_message":
            content = payload.get("message")
            room_id = payload.get("room_id")
            recipient_id = payload.get("recipient_id")

            if not content or not content.strip():
                return

            room_id = int(room_id) if room_id else None
            recipient_id = int(recipient_id) if recipient_id else None

            # Open a DB session to save the message
            with SessionLocal() as db:
                # Verify sender exists
                sender = db.query(User).filter(User.id == user_id).first()
                if not sender:
                    return
                sender_username = sender.username

                # Create message
                new_msg = Message(
                    sender_id=user_id,
                    room_id=room_id,
                    recipient_id=recipient_id,
                    content=content
                )
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)
                
                # Structure message payload for clients
                response_payload = {
                    "id": new_msg.id,
                    "sender_id": user_id,
                    "sender_username": sender_username,
                    "room_id": room_id,
                    "recipient_id": recipient_id,
                    "content": content,
                    "created_at": new_msg.created_at.isoformat(),
                    "is_read": False
                }

            response = {
                "type": "chat_message",
                "payload": response_payload
            }

            if room_id:
                # Broadcast message to all room members
                await self.broadcast_to_room(room_id, response)
            elif recipient_id:
                # Private message: Send to recipient AND sender (so it appears on both screen logs)
                await self.send_personal_message(response, recipient_id)
                await self.send_personal_message(response, user_id)

# Global connection manager instance
manager = ConnectionManager()

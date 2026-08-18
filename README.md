# Progressively Scalable Real-Time Chat Application

A high-performance, progressive Real-Time Chat Application built using **FastAPI**, **WebSockets**, **SQLAlchemy (SQLite/MySQL)**, and **JWT Authentication** on the backend, paired with a stunning glassmorphic vanilla JavaScript/CSS frontend.

This repository is structured progressively to demonstrate advanced backend engineering concepts—ranging from basic WebSockets up to database pooling, authentication, search, and containerization.

---

## 🏗️ Project Architecture

```
User A (Browser) ── WebSocket ──┐
                                │
                                ▼
                         FastAPI Server (main.py)
                                │
                        WebSocket Manager (manager.py)
                                │
                                ▼
                       MySQL / SQLite Database
                                ▲
                                │
User B (Browser) ── WebSocket ──┘
```

The server manages a persistent, full-duplex TCP connection (WebSocket) for each user. When User A sends a message, the server parses the payload, writes it to the database, and immediately pushes it (broadcasts) to User B without User B needing to refresh or poll the server.

---

## 📂 Project Structure

```
realtime-chat/
│
├── app/
│   ├── api/
│   │   ├── auth.py                 # Register, Login endpoints
│   │   ├── users.py                # User profiles and lists
│   │   └── messages.py             # Room listing, DM & group histories, search
│   │
│   ├── database/
│   │   └── connection.py           # DB Engine, sessionmaker, and get_db dependency
│   │
│   ├── models/
│   │   ├── base.py                 # Base model decleration
│   │   ├── user.py                 # User model (hashed credentials & status)
│   │   ├── room.py                 # Chat room model
│   │   └── message.py              # Message model (both room & private chats)
│   │
│   ├── schemas/
│   │   ├── user.py                 # Pydantic validation schemas for Auth
│   │   ├── room.py                 # Pydantic schemas for Rooms
│   │   └── message.py              # Pydantic schemas for Messages
│   │
│   ├── services/
│   │   ├── auth_service.py         # Password hashing & JWT operations
│   │   └── chat_service.py         # DB operations for messages and rooms
│   │
│   ├── websocket/
│   │   └── manager.py              # WebSocket connection & broadcasting manager
│   │
│   └── main.py                     # FastAPI server, Lifespan configuration, static mount
│
├── frontend/                       # Glassmorphic premium client app
│   ├── index.html                  # Welcome page (Login / Register forms)
│   ├── chat.html                   # Dashboard workspace
│   ├── style.css                   # Glassmorphic CSS Styling
│   └── chat.js                     # WebSocket broker & client event loop
│
├── tests/
│   └── test_chat.py                # Automated Test Suite (pytest)
│
├── Dockerfile                      # App container
├── docker-compose.yml              # Multi-container setup (API + MySQL + Redis)
├── requirements.txt                # Python dependencies
├── .env.example                    # Env configurations template
└── .gitignore                      # Git ignored files
```

---

## ⚡ Quick Start (Local Run - SQLite)

To run the application locally on your machine:

### 1. Set up a Virtual Environment
```bash
# Create environment
python -m venv venv

# Activate on Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Or Windows (CMD)
.\venv\Scripts\activate.bat
# Or macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Environment variables
Copy the template `.env.example` file to `.env`:
```bash
copy .env.example .env
```
By default, the `.env` uses SQLite: `DATABASE_URL=sqlite:///./chat.db`. The application automatically creates the database file on startup!

### 4. Spin up the Server
```bash
uvicorn app.main:app --reload
```
Open your browser and visit: [http://localhost:8000](http://localhost:8000)

---

## 🐳 Docker Compose Run (MySQL + Redis)

To run the application in a production-like setting using MySQL and Redis:

```bash
docker-compose up --build
```
This command starts:
1. **FastAPI Application** on port `8000`.
2. **MySQL 8.0 Database** on port `3306` (stores users, rooms, and chat logs).
3. **Redis Cache** on port `6379`.

The FastAPI service has a health check that waits until MySQL is healthy before starting.

---

## 🧪 Running Tests
To run the integration and unit tests:
```bash
pytest tests/
```
The test suite overrides the database dependency to use a temporary database (`test_chat.db`) and cleans up the file after completing the assertions.

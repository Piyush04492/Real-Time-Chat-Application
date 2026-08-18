import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database.connection import Base, get_db
from app.models.room import Room

# Use a separate database file for tests
TEST_DB_URL = "sqlite:///./test_chat.db"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency override
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Override the database dependency in the FastAPI application
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown_database():
    """Fixture to build tables before tests and delete the test DB after."""
    # Build tables
    Base.metadata.create_all(bind=engine)
    
    # Initialize some mock data
    db = TestingSessionLocal()
    db.add(Room(name="TestGeneral", description="General test room"))
    db.commit()
    db.close()
    
    yield
    
    # Tear down tables and delete file
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_chat.db"):
        os.remove("./test_chat.db")

# --- AUTHENTICATION TESTS ---

def test_user_registration():
    """Test registering a new user."""
    response = client.post(
        "/api/auth/register",
        json={"username": "testuser", "password": "testpassword123"}
    )
    assert response.status_code == 201
    assert response.json()["username"] == "testuser"
    assert "id" in response.json()

def test_user_registration_duplicate():
    """Test registering a username that is already taken."""
    response = client.post(
        "/api/auth/register",
        json={"username": "testuser", "password": "newpassword123"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already registered"

def test_user_login_success():
    """Test logging in with valid credentials."""
    response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "testpassword123"}
    )
    assert response.status_code == 200
    json_data = response.json()
    assert "access_token" in json_data
    assert json_data["token_type"] == "bearer"

def test_user_login_wrong_password():
    """Test logging in with incorrect credentials."""
    response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"

# --- PROTECTED ROUTE TESTS ---

def test_get_current_user_unauthorized():
    """Test accessing protected user endpoint without auth token."""
    response = client.get("/api/users/me")
    assert response.status_code == 401

def test_get_current_user_authorized():
    """Test accessing protected user endpoint with valid JWT token."""
    # Login to get token
    login_response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "testpassword123"}
    )
    token = login_response.json()["access_token"]
    
    # Access profile route
    response = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"

# --- ROOMS & MESSAGES TESTS ---

def test_get_rooms():
    """Test retrieving lists of chat rooms."""
    login_response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "testpassword123"}
    )
    token = login_response.json()["access_token"]
    
    response = client.get(
        "/api/rooms",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    rooms_list = response.json()
    assert len(rooms_list) >= 1
    assert any(room["name"] == "TestGeneral" for room in rooms_list)

def test_create_room():
    """Test creating a new chat room."""
    login_response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "testpassword123"}
    )
    token = login_response.json()["access_token"]
    
    response = client.post(
        "/api/rooms",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Science", "description": "Discuss quantum physics"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Science"
    assert response.json()["description"] == "Discuss quantum physics"

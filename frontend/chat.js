// --- STATE MANAGEMENT ---
let ws = null;
let currentUserId = null;
let currentUsername = localStorage.getItem('username');
let currentToken = localStorage.getItem('token');

let activeChatType = null; // 'room' or 'private'
let activeChatId = null;   // room_id or user_id
let activeChatName = '';

let rooms = [];
let users = [];
let onlineUserIds = new Set();
let typingTimeouts = {}; // Track typing timeout for other users
let isTypingSent = false;
let typingDebounceTimer = null;

// --- CONFIG & URLS ---
const API_URL = '/api';
const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
const WS_URL = `${wsScheme}://${window.location.host}/ws`;

// Redirect if unauthenticated
if (!currentToken) {
    window.location.href = '/';
}

// Helper: standard headers
function getHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`
    };
}

// --- DOM ELEMENTS ---
const myUsernameEl = document.getElementById('my-username');
const myAvatarEl = document.getElementById('my-avatar');
const logoutBtn = document.getElementById('logout-btn');

const roomsListEl = document.getElementById('rooms-list');
const usersListEl = document.getElementById('users-list');

const activeChatTitle = document.getElementById('active-chat-title');
const activeChatDesc = document.getElementById('active-chat-description');
const activeChatAvatar = document.getElementById('active-chat-avatar');

const messagesContainer = document.getElementById('messages-container');
const welcomeScreen = document.getElementById('welcome-screen');
const messageForm = document.getElementById('message-form');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');

const typingIndicatorBar = document.getElementById('typing-indicator-bar');
const typingText = document.getElementById('typing-text');

const msgSearchInput = document.getElementById('msg-search-input');
const clearSearchBtn = document.getElementById('clear-search-btn');
const searchIndicator = document.getElementById('search-indicator');
const closeSearchIndicatorBtn = document.getElementById('close-search-indicator-btn');

// Modal Elements
const createRoomModal = document.getElementById('create-room-modal');
const openCreateRoomModalBtn = document.getElementById('open-create-room-modal');
const closeRoomModalBtn = document.getElementById('close-room-modal');
const createRoomForm = document.getElementById('create-room-form');
const createRoomError = document.getElementById('create-room-error');

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', async () => {
    // Set my username and avatar
    myUsernameEl.innerText = currentUsername || 'User';
    myAvatarEl.innerText = currentUsername ? currentUsername.substring(0, 2).toUpperCase() : 'U';

    // 1. Fetch my profile to verify token and get my user ID
    await fetchMyProfile();

    // 2. Fetch rooms and users lists
    await fetchRooms();
    await fetchUsers();

    // 3. Connect WebSockets
    connectWebSocket();

    // 4. Bind event listeners
    bindEvents();
});

// --- API FETCH OPERATIONS ---

async function fetchMyProfile() {
    try {
        const res = await fetch(`${API_URL}/users/me`, { headers: getHeaders() });
        if (!res.ok) {
            // Token expired or invalid
            handleLogout();
            return;
        }
        const data = await res.json();
        currentUserId = data.id;
    } catch (err) {
        console.error('Error fetching profile:', err);
    }
}

async function fetchRooms() {
    try {
        const res = await fetch(`${API_URL}/rooms`, { headers: getHeaders() });
        if (res.ok) {
            rooms = await res.json();
            renderRoomsList();
        }
    } catch (err) {
        console.error('Error fetching rooms:', err);
    }
}

async function fetchUsers() {
    try {
        const res = await fetch(`${API_URL}/users`, { headers: getHeaders() });
        if (res.ok) {
            users = await res.json();
            renderUsersList();
        }
    } catch (err) {
        console.error('Error fetching users:', err);
    }
}

// --- RENDER FUNCTIONS ---

function renderRoomsList() {
    roomsListEl.innerHTML = '';
    if (rooms.length === 0) {
        roomsListEl.innerHTML = '<li class="list-loader">No rooms available.</li>';
        return;
    }

    rooms.forEach(room => {
        const li = document.createElement('li');
        li.dataset.id = room.id;
        li.dataset.type = 'room';
        if (activeChatType === 'room' && activeChatId === room.id) {
            li.classList.add('active');
        }

        const avatarInitial = room.name.substring(0, 2).toUpperCase();
        li.innerHTML = `
            <div class="avatar item-avatar" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%)">#</div>
            <div class="item-details">
                <span class="item-name">${room.name}</span>
                <span class="item-subtext">${room.description || 'No description'}</span>
            </div>
        `;

        li.addEventListener('click', () => selectChat('room', room.id, room.name, room.description));
        roomsListEl.appendChild(li);
    });
}

function renderUsersList() {
    usersListEl.innerHTML = '';
    if (users.length === 0) {
        usersListEl.innerHTML = '<li class="list-loader">No users registered.</li>';
        return;
    }

    users.forEach(user => {
        const isOnline = onlineUserIds.has(user.id);
        const li = document.createElement('li');
        li.dataset.id = user.id;
        li.dataset.type = 'private';
        if (activeChatType === 'private' && activeChatId === user.id) {
            li.classList.add('active');
        }

        const initial = user.username.substring(0, 2).toUpperCase();
        li.innerHTML = `
            <div class="avatar item-avatar">${initial}</div>
            <div class="item-details">
                <span class="item-name">${user.username}</span>
                <span class="item-subtext"><span class="status-dot ${isOnline ? 'online' : 'offline'}"></span> ${isOnline ? 'Online' : 'Offline'}</span>
            </div>
        `;

        li.addEventListener('click', () => selectChat('private', user.id, user.username, isOnline ? 'Online' : 'Offline'));
        usersListEl.appendChild(li);
    });
}

// --- WEBSOCKET CONNECTION & HANDLER ---

function connectWebSocket() {
    if (ws) {
        ws.close();
    }

    // Connect with JWT token inside query parameters
    ws = new WebSocket(`${WS_URL}?token=${currentToken}`);

    ws.onopen = () => {
        console.log('WebSocket Connection Opened.');
        // Re-join active room if connection dropped and re-established
        if (activeChatType === 'room') {
            sendWsMessage('join_room', { room_id: activeChatId });
        }
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const type = data.type;
        const payload = data.payload;

        switch (type) {
            case 'online_users_list':
                // Update local online tracking set
                onlineUserIds.clear();
                payload.users.forEach(u => onlineUserIds.add(u.id));
                renderUsersList();
                // If current chat is private, update subtext status
                if (activeChatType === 'private') {
                    const isOnline = onlineUserIds.has(activeChatId);
                    activeChatDesc.innerHTML = `<span class="status-dot ${isOnline ? 'online' : 'offline'}"></span> ${isOnline ? 'Online' : 'Offline'}`;
                }
                break;

            case 'chat_message':
                handleIncomingChatMessage(payload);
                break;

            case 'typing':
                handleIncomingTypingIndicator(payload);
                break;
                
            default:
                console.log('Unknown socket event type:', type);
        }
    };

    ws.onclose = (event) => {
        console.log('WebSocket closed. Reconnecting in 3 seconds...', event);
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => {
        console.error('WebSocket Error:', err);
    };
}

function sendWsMessage(type, payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type, payload }));
    }
}

// --- CHAT SELECTION & HISTORY LOADING ---

async function selectChat(type, id, name, description) {
    if (activeChatType === type && activeChatId === id) return;

    // Remove active highlight from previous sidebar elements
    document.querySelectorAll('.item-list li').forEach(li => li.classList.remove('active'));
    
    // Highlight selected item
    const selectedEl = document.querySelector(`.item-list li[data-type="${type}"][data-id="${id}"]`);
    if (selectedEl) selectedEl.classList.add('active');

    // 1. Leave current room if changing rooms
    if (activeChatType === 'room') {
        sendWsMessage('leave_room', { room_id: activeChatId });
    }

    // Set new active chat state
    activeChatType = type;
    activeChatId = id;
    activeChatName = name;

    // Reset searching indicators if switching chats
    searchIndicator.style.display = 'none';

    // Update Chat Panel Header
    activeChatTitle.innerText = name;
    
    if (type === 'room') {
        activeChatDesc.innerText = description || 'No description';
        activeChatAvatar.innerText = '#';
        activeChatAvatar.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
        
        // Join new room on WebSocket
        sendWsMessage('join_room', { room_id: id });
    } else {
        const isOnline = onlineUserIds.has(id);
        activeChatDesc.innerHTML = `<span class="status-dot ${isOnline ? 'online' : 'offline'}"></span> ${isOnline ? 'Online' : 'Offline'}`;
        activeChatAvatar.innerText = name.substring(0,2).toUpperCase();
        activeChatAvatar.style.background = 'var(--primary-grad)';
    }

    // Hide welcome overlay & enable inputs
    welcomeScreen.style.display = 'none';
    messageInput.disabled = false;
    sendBtn.disabled = false;
    messageInput.placeholder = `Message ${type === 'room' ? '#' : ''}${name}...`;
    messageInput.value = '';
    messageInput.focus();

    // Clear typing indicators bar
    typingIndicatorBar.style.display = 'none';

    // Fetch and render message history
    await loadChatHistory();
}

async function loadChatHistory() {
    messagesContainer.innerHTML = '<div class="list-loader"><i class="fa-solid fa-spinner fa-spin"></i> Loading chat log...</div>';
    
    let endpoint = '';
    if (activeChatType === 'room') {
        endpoint = `${API_URL}/rooms/${activeChatId}/messages`;
    } else {
        endpoint = `${API_URL}/messages/private/${activeChatId}`;
    }

    try {
        const res = await fetch(endpoint, { headers: getHeaders() });
        if (res.ok) {
            const messages = await res.json();
            messagesContainer.innerHTML = '';
            
            if (messages.length === 0) {
                messagesContainer.innerHTML = '<div class="system-message">This is the start of your message history.</div>';
                return;
            }

            renderMessages(messages);
            scrollToBottom();
        }
    } catch (err) {
        console.error('Error loading messages:', err);
        messagesContainer.innerHTML = '<div class="system-message">Error loading history.</div>';
    }
}

// Render list of messages
function renderMessages(messages) {
    let lastDateStr = null;

    messages.forEach(msg => {
        // Date separator logic
        const msgDate = new Date(msg.created_at);
        const dateStr = msgDate.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
        
        if (dateStr !== lastDateStr) {
            const dateDiv = document.createElement('div');
            dateDiv.className = 'date-divider';
            dateDiv.innerText = dateStr;
            messagesContainer.appendChild(dateDiv);
            lastDateStr = dateStr;
        }

        appendMessageBubble(msg);
    });
}

function appendMessageBubble(msg) {
    const isOutgoing = msg.sender_id === currentUserId;
    const msgWrapper = document.createElement('div');
    msgWrapper.className = `message-wrapper ${isOutgoing ? 'outgoing' : 'incoming'}`;
    msgWrapper.dataset.msgId = msg.id;

    // Format local time
    const msgTime = new Date(msg.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

    // Build internal content
    let senderHeader = '';
    if (!isOutgoing && activeChatType === 'room') {
        senderHeader = `<div class="msg-sender">${msg.sender_username}</div>`;
    }

    // Delivery checkmark details for Level 4 status (Outgoing DMs)
    const checkmark = isOutgoing && activeChatType === 'private' 
        ? `<i class="fa-solid fa-check${msg.is_read ? '-double' : ''}" style="color: ${msg.is_read ? '#00ff87' : 'inherit'}"></i>` 
        : '';

    msgWrapper.innerHTML = `
        ${senderHeader}
        <div class="msg-bubble">
            ${msg.content}
            <div class="msg-footer">
                <span>${msgTime}</span>
                ${checkmark}
            </div>
        </div>
    `;

    messagesContainer.appendChild(msgWrapper);
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// --- MESSAGE SENDING HANDLER ---

messageForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = messageInput.value.trim();
    if (!text || !activeChatId) return;

    // Send via socket
    const payload = {};
    if (activeChatType === 'room') {
        payload.room_id = activeChatId;
    } else {
        payload.recipient_id = activeChatId;
    }
    payload.message = text;

    sendWsMessage('chat_message', payload);

    // Reset input and typing status
    messageInput.value = '';
    triggerTypingStatus(false);
    isTypingSent = false;
    messageInput.focus();
});

// --- TYPING INDICATOR OPERATIONS ---

function triggerTypingStatus(isTyping) {
    const payload = {};
    if (activeChatType === 'room') {
        payload.room_id = activeChatId;
    } else {
        payload.recipient_id = activeChatId;
    }
    payload.is_typing = isTyping;

    sendWsMessage('typing', payload);
}

function handleTypingInput() {
    if (!isTypingSent) {
        isTypingSent = true;
        triggerTypingStatus(true);
    }

    // Debounce: Clear any existing timers, then set a new one
    clearTimeout(typingDebounceTimer);
    typingDebounceTimer = setTimeout(() => {
        triggerTypingStatus(false);
        isTypingSent = false;
    }, 2000);
}

function handleIncomingTypingIndicator(payload) {
    // Make sure typing user is NOT us, and corresponds to the active panel
    if (payload.user_id === currentUserId) return;

    const isMatch = (activeChatType === 'room' && payload.room_id === activeChatId) ||
                    (activeChatType === 'private' && payload.recipient_id === currentUserId && payload.user_id === activeChatId);

    if (!isMatch) return;

    const typistId = payload.user_id;

    if (payload.is_typing) {
        // Show typing indicator
        typingText.innerText = `${payload.username} is typing...`;
        typingIndicatorBar.style.display = 'block';
        scrollToBottom();

        // Fallback: Clear typing status if we don't get is_typing: false in 5 seconds
        clearTimeout(typingTimeouts[typistId]);
        typingTimeouts[typistId] = setTimeout(() => {
            typingIndicatorBar.style.display = 'none';
        }, 5000);
    } else {
        // Hide typing indicator
        clearTimeout(typingTimeouts[typistId]);
        typingIndicatorBar.style.display = 'none';
    }
}

function handleIncomingChatMessage(msg) {
    const isCurrentRoom = activeChatType === 'room' && msg.room_id === activeChatId;
    const isCurrentDM = activeChatType === 'private' && msg.room_id === null &&
                        ((msg.sender_id === activeChatId && msg.recipient_id === currentUserId) || 
                         (msg.sender_id === currentUserId && msg.recipient_id === activeChatId));

    if (isCurrentRoom || isCurrentDM) {
        appendMessageBubble(msg);
        scrollToBottom();
        
        // Clear matching typing indicator immediately
        typingIndicatorBar.style.display = 'none';
        if (msg.sender_id !== currentUserId) {
            clearTimeout(typingTimeouts[msg.sender_id]);
        }
    }
}

// --- MESSAGE SEARCH OPERATIONS (Level 4) ---

let searchDebounceTimer = null;
msgSearchInput.addEventListener('input', () => {
    const q = msgSearchInput.value.trim();
    if (q.length > 0) {
        clearSearchBtn.style.display = 'block';
    } else {
        clearSearchBtn.style.display = 'none';
    }

    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        if (q.length >= 2) {
            executeSearch(q);
        } else if (q.length === 0) {
            clearSearch();
        }
    }, 4000); // 400ms debounce
});

clearSearchBtn.addEventListener('click', () => {
    msgSearchInput.value = '';
    clearSearchBtn.style.display = 'none';
    clearSearch();
});

async function executeSearch(q) {
    searchIndicator.style.display = 'flex';
    messagesContainer.innerHTML = `<div class="list-loader"><i class="fa-solid fa-spinner fa-spin"></i> Searching database for "${q}"...</div>`;

    try {
        const res = await fetch(`${API_URL}/messages/search?q=${encodeURIComponent(q)}`, { headers: getHeaders() });
        if (res.ok) {
            const results = await res.json();
            messagesContainer.innerHTML = '';
            
            if (results.length === 0) {
                messagesContainer.innerHTML = `<div class="system-message">No messages found matching "${q}".</div>`;
                return;
            }

            renderMessages(results);
            scrollToBottom();
        }
    } catch (err) {
        console.error('Search error:', err);
    }
}

function clearSearch() {
    searchIndicator.style.display = 'none';
    if (activeChatId) {
        loadChatHistory();
    } else {
        messagesContainer.innerHTML = '';
        welcomeScreen.style.display = 'flex';
    }
}

closeSearchIndicatorBtn.addEventListener('click', () => {
    msgSearchInput.value = '';
    clearSearchBtn.style.display = 'none';
    clearSearch();
});

// --- EVENT BINDING & GENERAL UTILS ---

function bindEvents() {
    logoutBtn.addEventListener('click', handleLogout);

    // Typing listener
    messageInput.addEventListener('input', handleTypingInput);

    // Modal Control for Creating Rooms
    openCreateRoomModalBtn.addEventListener('click', () => {
        createRoomModal.style.display = 'flex';
        createRoomForm.reset();
        createRoomError.style.display = 'none';
        document.getElementById('new-room-name').focus();
    });

    closeRoomModalBtn.addEventListener('click', () => {
        createRoomModal.style.display = 'none';
    });

    // Close modal on background click
    createRoomModal.addEventListener('click', (e) => {
        if (e.target === createRoomModal) {
            createRoomModal.style.display = 'none';
        }
    });

    // Handle Room Creation Submission
    createRoomForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        createRoomError.style.display = 'none';

        const name = document.getElementById('new-room-name').value.trim();
        const description = document.getElementById('new-room-desc').value.trim();

        try {
            const res = await fetch(`${API_URL}/rooms`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({ name, description })
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.detail || 'Failed to create room.');
            }

            // Hide modal & refresh rooms
            createRoomModal.style.display = 'none';
            await fetchRooms();
            
            // Auto-select the newly created room
            selectChat('room', data.id, data.name, data.description);

        } catch (err) {
            createRoomError.innerText = err.message;
            createRoomError.style.display = 'block';
        }
    });
}

function handleLogout() {
    // Notify server offline status by setting is_online = false (usually handled by WS disconnect, but let's clear local storage)
    if (ws) {
        ws.close();
    }
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    window.location.href = '/';
}

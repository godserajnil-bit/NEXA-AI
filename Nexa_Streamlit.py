# app.py — Nexa Streamlit (OpenRouter) version
# Dark theme, gpt-3.5-turbo, simple SQLite auth
# Usage:
#   export OPENROUTER_API_KEY="your_openrouter_key"
#   pip install -r requirements.txt
#   streamlit run app.py

import sys, io, os

# --- Safe UTF-8 setup for Render ---
try:
    # Set environment variable for UTF-8 encoding
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["LANG"] = "en_US.UTF-8"

    # Only reconfigure if stdout/stderr are open and have a buffer
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception as e:
    # Don’t crash app if Render closes stdout early
    pass

import sqlite3
import requests
import tempfile
from datetime import datetime
from pathlib import Path
import html
from PIL import Image
import streamlit as st
# ✅ Must be FIRST Streamlit command
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")

# --- Initialize session state ---
if "user" not in st.session_state:
    st.session_state.user = None
if "conv_id" not in st.session_state:
    st.session_state.conv_id = None
if "persona" not in st.session_state:
    st.session_state.persona = "Friendly"

# --- Initialize Database ---
def init_db():
    conn = sqlite3.connect("nexa.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            sender TEXT,
            role TEXT,
            content TEXT,
            image BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# --- FORCE RESET DATABASE SCHEMA (run once to fix schema) ---
DB_PATH = "nexa.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    try:
        print("🗑️ Old database deleted — rebuilding...")
    except Exception:
        pass

init_db()
try:
    print("✅ Database rebuilt with correct schema.")
except Exception:
    pass

# --- AI Reply Function ---
def get_ai_reply(prompt, persona="Neutral"):
    """Fetch an AI-generated reply from OpenRouter."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return "⚠️ Missing OpenRouter API key. Please set OPENROUTER_API_KEY in your environment."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nexa-ai.streamlit.app/",
        "X-Title": "Nexa AI",
    }

    data = {
        "model": "meta-llama/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": f"You are a {persona} assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 400,
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        if response.status_code != 200:
            msg = response.text.encode('utf-8', 'ignore').decode('utf-8')
            return f"⚠️ API Error {response.status_code}: {msg}"

        reply = response.json()["choices"][0]["message"]["content"].strip()
        return reply.encode('utf-8', 'ignore').decode('utf-8')

    except Exception as e:
        err_msg = str(e).encode('utf-8', 'ignore').decode('utf-8')
        return f"⚠️ OpenRouter error: {err_msg}"

# --- Chat Section ---
st.markdown("### 💬 Chat")

# Create message list if not exists
if "messages" not in st.session_state:
    st.session_state.messages = []

# Show chat history
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f"🧑‍💬 **You:** {msg['content']}")
    else:
        st.markdown(f"🤖 **Nexa:** {msg['content']}")

# User input box
user_input = st.chat_input("Type your message...")

if user_input:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Generate AI reply
    with st.spinner("Nexa is thinking..."):
        ai_reply = get_ai_reply(user_input, st.session_state.get("persona", "Neutral"))

    # Add assistant message
    st.session_state.messages.append({"role": "assistant", "content": ai_reply})

    # ✅ Corrected this line (missing parenthesis)
    st.rerun()

# ---------------------------
# Configuration
# ---------------------------
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = "nexa_streamlit.db"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = "gpt-3.5-turbo"  # default model (OpenRouter-compatible)

# ---------------------------
# Database helpers
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            title TEXT,
            created TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            sender TEXT,
            role TEXT,
            content TEXT,
            image_path TEXT,
            timestamp TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------
# Core DB operations
# ---------------------------
def create_user(username: str, password: str):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
    conn.commit(); conn.close()

def verify_user(username: str, password: str) -> bool:
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    row = c.fetchone(); conn.close()
    return bool(row and row["password"] == password)

def create_conversation(user: str, title: str = "New chat"):
    conn = get_conn(); c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("INSERT INTO conversations (user, title, created) VALUES (?, ?, ?)", (user, title, now))
    conn.commit(); cid = c.lastrowid; conn.close(); return cid

def list_conversations(user: str):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, title, created FROM conversations WHERE user=? ORDER BY id DESC", (user,))
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]

def rename_conversation_if_default(cid: int, new_title: str):
    if not new_title: return
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (row["title"] is None or row["title"].strip() == "" or row["title"] == "New chat"):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid))
        conn.commit()
    conn.close()

def save_message(conv_id: int, sender: str, role: str, content: str = None, image_path: str = None):
    ts = datetime.utcnow().isoformat()
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, image_path, timestamp) VALUES (?,?,?,?,?,?)",
              (conv_id, sender, role, content, image_path, ts))
    conn.commit(); conn.close()

def load_messages(conv_id: int):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT sender, role, content, image_path, timestamp FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]

# ---------------------------
# Utility
# ---------------------------
STOPWORDS = {"the","and","for","that","with","this","what","when","where","which","would","could","should","there","their","about","your","from","have","just","like","also","been","they","them","will","how","can","a","an","in","on","of","to","is","are","it"}

def simple_main_motive(text: str, max_words: int = 5) -> str:
    if not text: return "New chat"
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    words = [w for w in cleaned.split() if w and len(w) > 2 and w not in STOPWORDS]
    if not words:
        s = text.strip()
        return (s[:40] + "...") if len(s) > 40 else s
    chosen = []
    seen = set()
    for w in words:
        if w in seen: continue
        seen.add(w); chosen.append(w)
        if len(chosen) >= max_words: break
    return " ".join(chosen).capitalize() if chosen else "New chat"

# ---------------------------
# OpenRouter call
# ---------------------------
def call_openrouter(messages, model=MODEL, timeout=30):
    """
    messages: list of dicts like {"role":"system","content":"..."} / {"role":"user","content":"..."}
    returns: assistant text (str) or raises Exception
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment.")
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages}
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "choices" in data and len(data["choices"]) > 0:
        content = data["choices"][0].get("message", {}).get("content", "")
        if content is None: content = ""
        return content
    else:
        raise RuntimeError(f"Unexpected response: {data}")

# ---------------------------
# Streamlit UI helpers (CSS + render)
# ---------------------------
def local_css():
    st.markdown(
        """
        <style>
        /* page */
        .stApp { background: linear-gradient(180deg,#070809,#0b0c10); color: #e6f9ff; }

        /* containers */
        .chat-box { background: rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.03); border-radius:12px; padding:12px; max-height:60vh; overflow:auto; }

        /* bubbles */
        .bubble-user { background:#0f1720; color:#e6f9ff; padding:10px 12px; border-radius:12px; margin:8px 0; display:inline-block; border:1px solid rgba(255,255,255,0.02); }
        .bubble-ai { background: linear-gradient(180deg, rgba(0,240,255,0.06), rgba(0,240,255,0.02)); color:#001; padding:10px 12px; border-radius:12px; margin:8px 0; display:inline-block; border:1px solid rgba(0,240,255,0.06); }

        .meta { color:#9fb8c9; font-size:12px; margin-bottom:6px; }
        .sidebar-box { background:transparent; border-radius:8px; padding:8px; }
        .small { font-size:13px; color:#9fb8c9; }

        /* narrow layout tweaks */
        @media (max-width: 800px) {
            .chat-box { max-height:50vh; }
        }
        </style>
        """, unsafe_allow_html=True
    )

def render_chat_messages(messages):
    """Display chat messages in styled bubbles."""
    container = st.container()
    with container:
        st.markdown('<div class="chat-box">', unsafe_allow_html=True)

        for msg in messages:
            role = msg.get("role", "")
            sender = msg.get("sender", "")
            content = msg.get("content", "") or ""
            image_path = msg.get("image_path", None)
            ts = msg.get("timestamp", "")

            # Show metadata
            meta = f"<div class='meta'>{sender} • {ts}</div>"
            st.markdown(meta, unsafe_allow_html=True)

            # Render message based on role
            if role == "assistant":
                safe_content = html.escape(content).replace("\n", "<br/>")
                st.markdown(f"<div class='bubble-ai'>{safe_content}</div>", unsafe_allow_html=True)

                if image_path:
                    try:
                        image = Image.open(image_path)
                        st.image(image, caption="AI Response Image", use_column_width=True)
                    except Exception as e:
                        st.warning(f"Could not load image: {e}")

            elif role == "user":
                safe_content = html.escape(content).replace("\n", "<br/>")
                st.markdown(f"<div class='bubble-user'>{safe_content}</div>", unsafe_allow_html=True)

                if image_path:
                    try:
                        st.image(str(image_path), width=360)
                    except Exception:
                        pass

        st.markdown("</div>", unsafe_allow_html=True)

# --- Sidebar: login/register or actions ---
with st.sidebar:
    st.markdown("## Nexa — Assistant")

    # If user not logged in
    if not st.session_state.user:
        st.markdown("### Login")
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pw")

        if st.button("Login"):
            if verify_user(username, password):
                st.session_state.user = username
                st.success(f"Logged in as {username}")
                if st.session_state.conv_id is None:
                    st.session_state.conv_id = create_conversation(username)
                st.rerun()
            else:
                st.error("Invalid credentials")

        st.markdown("---")
        st.markdown("### Register")
        r_user = st.text_input("New username", key="reg_user")
        r_pw = st.text_input("New password", type="password", key="reg_pw")

        if st.button("Register"):
            if not r_user or not r_pw:
                st.warning("Provide both username and password")
            else:
                try:
                    create_user(r_user, r_pw)
                    st.success("Registered. You can now login.")
                except Exception as e:
                    st.error(f"Could not register: {e}")

        st.markdown("---")
        st.caption("App uses an environment OpenRouter API key for AI replies.")

    # --- User Logged In Section ---
    else:
        st.markdown(f"**Logged in:** {st.session_state.user}")

        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.conv_id = None
            st.rerun()

        st.markdown("---")
        st.markdown("### Conversations")

        # --- Fetch Conversations from Database ---
        def get_conversations(user_id=None):
            """Fetch all conversations (optionally filtered by user)."""
            conn = get_conn()
            cur = conn.cursor()
            if user_id:
                cur.execute(
                    "SELECT id, created_at FROM conversations WHERE user_id=? ORDER BY created_at DESC",
                    (user_id,),
                )
            else:
                cur.execute("SELECT id, created_at FROM conversations ORDER BY created_at DESC")
            rows = cur.fetchall()
            conn.close()
            return [{"id": r[0], "created_at": r[1]} for r in rows]

        # --- Conversation Management ---
        conversations = get_conversations(st.session_state.user)
        if conversations:
            for c in conversations:
                st.write(f"🗂️ Conversation ID: {c['id']} — Created: {c['created_at']}")
                if st.button(f"🗑️ Delete {c['id']}", key=f"del_{c['id']}"):
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute("DELETE FROM messages WHERE conversation_id=?", (c["id"],))
                    cur.execute("DELETE FROM conversations WHERE id=?", (c["id"],))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Conversation {c['id']} deleted")
                    st.rerun()
        else:
            st.info("No conversations found yet.")

        st.markdown("---")
        # persona
        st.markdown("### Persona")
        p = st.selectbox(
            "Choose assistant style",
            ["Friendly", "Neutral", "Cheerful", "Professional"],
            index=["Friendly", "Neutral", "Cheerful", "Professional"].index(st.session_state.persona),
            key="persona_select"
        )
        st.session_state.persona = p
        st.markdown("---")

        # NEW conversation
        if st.button("New chat (clear view)"):
            st.session_state.conv_id = create_conversation(st.session_state.user)
            st.rerun()

# --- Main UI ---
if not st.session_state.user:
    st.markdown(
        "<div style='padding:30px'><h2 style='color:#dff9ff'>Welcome to Nexa</h2>"
        "<p class='small'>Please login or register in the sidebar to start.</p></div>",
        unsafe_allow_html=True
    )

else:
    left_col, right_col = st.columns([3, 1])
    with left_col:
        st.markdown("### Chat")

        # Ensure conversation ID exists
        if not st.session_state.conv_id:
            st.session_state.conv_id = create_conversation(st.session_state.user)

        # Load and render previous messages
        messages = load_messages(st.session_state.conv_id)
        render_chat_messages(messages)  # <-- your new message renderer

        # Input area
        with st.form("chat_input_form", clear_on_submit=False):
            user_text = st.text_area(
                "Message",
                key="user_msg",
                height=80,
                placeholder="Ask Nexa anything..."
            )
            uploaded_file = st.file_uploader(
                "Attach image (optional)",
                type=["png", "jpg", "jpeg", "gif"]
            )
            submit = st.form_submit_button("Send")

            if submit:
                # Save user message (and image if present)
                img_path = None
                if uploaded_file:
                    suffix = Path(uploaded_file.name).suffix
                    fname = f"{st.session_state.user}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{suffix}"
                    fpath = UPLOAD_DIR / fname
                    fpath.write_bytes(uploaded_file.read())
                    img_path = str(fpath)

                save_message(
                    st.session_state.conv_id,
                    st.session_state.user,
                    "user",
                    user_text or None,
                    img_path
                )

                if user_text:
                    rename_conversation_if_default(
                        st.session_state.conv_id,
                        simple_main_motive(user_text, max_words=5)
                    )

                # Prepare messages for LLM
                history = load_messages(st.session_state.conv_id)
                payload_messages = [
                    {
                        "role": "system",
                        "content": f"You are Nexa, a helpful assistant. Persona: {st.session_state.persona}."
                    }
                ]
                for m in history:
                    role = "assistant" if m["role"] == "assistant" else "user"
                    content = m["content"] or ""
                    payload_messages.append({"role": role, "content": content})

                payload_messages.append({"role": "user", "content": user_text or ""})

                # Generate assistant reply
                assistant_reply = ""
                try:
                    with st.spinner("Thinking..."):
                        assistant_reply = call_openrouter(payload_messages, model=MODEL)
                except Exception as e:
                    assistant_reply = f"(LLM error) {e}"

                if assistant_reply:
                    save_message(st.session_state.conv_id, "assistant", "assistant", assistant_reply, None)
                    st.rerun()

    # Sidebar info
    with right_col:
        st.markdown("### Info")
        st.markdown(f"**User:** {st.session_state.user}")
        st.markdown(f"**Conversation ID:** {st.session_state.conv_id}")
        st.markdown(f"**Persona:** {st.session_state.persona}")
        st.markdown("---")
        st.markdown("### Tips")
        st.markdown("- Use `news: topic` to fetch news (if GNews key configured).")
        st.markdown("- Upload images to show them in chat.")
        st.markdown("---")
        st.markdown("### App")
        st.markdown(
            "This app uses OpenRouter for AI replies. "
            "Make sure `OPENROUTER_API_KEY` is set in your environment."
        )

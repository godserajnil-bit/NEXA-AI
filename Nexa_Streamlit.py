# Nexa_Simple.py
# Simplified Nexa — clean layout, + upload button, same DB logic intact.

import os
import sys
import io
import sqlite3
import requests
from datetime import datetime, timezone
from pathlib import Path
import html
import streamlit as st

# ---------------------------
# Encoding fix
# ---------------------------
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------
# Config
# ---------------------------
st.set_page_config(page_title="Nexa", layout="wide")
DB_PATH = "nexa.db"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ---------------------------
# Database
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def reset_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS messages")
    c.execute("DROP TABLE IF EXISTS conversations")
    c.execute("DROP TABLE IF EXISTS users")
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

reset_db()

# ---------------------------
# Helper functions
# ---------------------------
def create_conversation(user, title="New chat"):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO conversations (user, title) VALUES (?, ?)", (user, title))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def list_conversations(user=None):
    conn = get_conn()
    c = conn.cursor()
    if user:
        c.execute("SELECT id, title FROM conversations WHERE user=? ORDER BY id DESC", (user,))
    else:
        c.execute("SELECT id, title FROM conversations ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def rename_conversation_if_default(cid, new_title):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (row["title"] == "New chat" or not row["title"]):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid))
        conn.commit()
    conn.close()

def save_message(conv_id, sender, role, content=None, image_path=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (conversation_id, sender, role, content, image_path) VALUES (?, ?, ?, ?, ?)",
        (conv_id, sender, role, content, image_path),
    )
    conn.commit()
    conn.close()

def load_messages(conv_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT sender, role, content, image_path FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------------------------
# Small helpers
# ---------------------------
STOPWORDS = {"the", "and", "for", "that", "with", "this", "what", "when", "where", "which", "would", "could", "should"}

def simple_main_motive(text):
    if not text:
        return "New chat"
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    words = [w for w in cleaned.split() if len(w) > 2 and w not in STOPWORDS]
    if not words:
        return text[:30]
    return " ".join(words[:5]).capitalize()

def call_openrouter(messages, model=MODEL):
    if not OPENROUTER_API_KEY:
        return "OpenRouter key missing — reply simulated."
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                      json={"model": model, "messages": messages}, headers=headers)
    data = r.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")

# ---------------------------
# CSS (Simple & Clean)
# ---------------------------
st.markdown("""
<style>
.stApp { background-color: #0d1117; color: #f0f6fc; }
.chat-bubble-user { background: #1f6feb; color: white; padding:10px 14px; border-radius:12px; margin:5px 0; width:fit-content; }
.chat-bubble-ai { background: #21262d; padding:10px 14px; border-radius:12px; margin:5px 0; width:fit-content; }
.sidebar-content { font-size: 15px; }
input, textarea { border-radius:8px !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session Init
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)

# ---------------------------
# Sidebar
# ---------------------------
with st.sidebar:
    st.markdown("## 💬 Nexa")
    if st.button("➕ New Chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()
    st.markdown("---")
    st.markdown("### Conversations")
    for conv in list_conversations(st.session_state.user):
        if st.button(conv["title"], key=f"conv_{conv['id']}"):
            st.session_state.conv_id = conv["id"]
            st.rerun()
    st.markdown("---")
    st.markdown("### Info", unsafe_allow_html=True)
    st.markdown(f"**User:** {st.session_state.user}")
    st.markdown(f"**Conversation ID:** {st.session_state.conv_id}")
    st.markdown("---")
    st.markdown("**Tips**\n- Use '+' to attach files\n- First message names chat\n- Minimal layout")

# ---------------------------
# Chat UI
# ---------------------------
st.markdown("### 💭 Chat")

messages = load_messages(st.session_state.conv_id)
for msg in messages:
    if msg["role"] == "assistant":
        st.markdown(f"<div class='chat-bubble-ai'>{html.escape(msg['content'])}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='chat-bubble-user'>{html.escape(msg['content'])}</div>", unsafe_allow_html=True)
    if msg["image_path"]:
        st.image(msg["image_path"], width=250)

# ---------------------------
# Input area (with + upload)
# ---------------------------
with st.container():
    cols = st.columns([8, 1])
    with cols[0]:
        user_text = st.text_input("Type your message...", key="input_msg")
    with cols[1]:
        uploaded = st.file_uploader("➕", type=["png", "jpg", "jpeg"], label_visibility="collapsed")

    if st.button("Send", type="primary"):
        img_path = None
        if uploaded:
            fname = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uploaded.name}"
            path = UPLOAD_DIR / fname
            path.write_bytes(uploaded.read())
            img_path = str(path)

        save_message(st.session_state.conv_id, st.session_state.user, "user", user_text, img_path)
        rename_conversation_if_default(st.session_state.conv_id, simple_main_motive(user_text))

        history = load_messages(st.session_state.conv_id)
        payload = [{"role": "system", "content": "You are Nexa, a helpful assistant."}]
        for m in history:
            role = "assistant" if m["role"] == "assistant" else "user"
            payload.append({"role": role, "content": m["content"] or ""})
        payload.append({"role": "user", "content": user_text or ""})

        try:
            reply = call_openrouter(payload)
        except Exception as e:
            reply = f"(Error: {e})"

        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)
        st.rerun()

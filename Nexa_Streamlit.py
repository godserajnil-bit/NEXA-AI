# Nexa_Streamlit_full.py
# Unified Nexa app — no login/register, includes reset_db() + chat history + motive titles
# Safe and complete

import sys
import io
import os
import sqlite3
import requests
from datetime import datetime, timezone
from pathlib import Path
import html
from PIL import Image
import streamlit as st

# ---------------------------
# UTF-8 Handling (safe)
# ---------------------------
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("LANG", "en_US.UTF-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------
# Streamlit Config
# ---------------------------
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")

DB_PATH = "nexa.db"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ---------------------------
# Database setup
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def reset_db():
    """Reset or initialize Nexa database."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS messages")
    c.execute("DROP TABLE IF EXISTS conversations")
    c.execute("DROP TABLE IF EXISTS users")
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)
    conn.commit()
    conn.close()

reset_db()  # rebuild db locally once

# ---------------------------
# DB helpers
# ---------------------------
def create_conversation(user, title="New chat"):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (user, title, created_at) VALUES (?, ?, ?)", (user, title, now))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def list_conversations(user=None):
    conn = get_conn()
    c = conn.cursor()
    if user:
        c.execute("SELECT id, title, created_at FROM conversations WHERE user=? ORDER BY created_at DESC", (user,))
    else:
        c.execute("SELECT id, title, created_at FROM conversations ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def rename_conversation_if_default(cid, new_title):
    if not new_title:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (not row["title"] or row["title"] == "New chat"):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid))
        conn.commit()
    conn.close()

def save_message(conv_id, sender, role, content=None, image_path=None):
    ts = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (conversation_id, sender, role, content, image_path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (conv_id, sender, role, content, image_path, ts),
    )
    conn.commit()
    conn.close()

def load_messages(conv_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT sender, role, content, image_path, created_at FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_conversation(conv_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    c.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit()
    conn.close()

# ---------------------------
# Utilities
# ---------------------------
STOPWORDS = {"the","and","for","that","with","this","what","when","where","which","would","could","should",
             "there","their","about","your","from","have","just","like","also","been","they","them","will",
             "how","can","a","an","in","on","of","to","is","are","it"}

def simple_main_motive(text, max_words=5):
    if not text:
        return "New chat"
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    words = [w for w in cleaned.split() if w and len(w) > 2 and w not in STOPWORDS]
    chosen, seen = [], set()
    for w in words:
        if w not in seen:
            seen.add(w)
            chosen.append(w)
        if len(chosen) >= max_words:
            break
    return " ".join(chosen).capitalize() if chosen else text[:40]

def call_openrouter(messages, model=MODEL, timeout=18):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set.")
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                      json={"model": model, "messages": messages},
                      headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "choices" in data and len(data["choices"]) > 0:
        return data["choices"][0].get("message", {}).get("content", "")
    return ""

# ---------------------------
# CSS + Chat rendering
# ---------------------------
def local_css():
    st.markdown("""
    <style>
    .stApp { background: #0b0c10; color: #e6f9ff; }
    .chat-box { background: rgba(255,255,255,0.05); padding:12px; border-radius:12px; max-height:60vh; overflow:auto; }
    .bubble-user { background:#111923; color:#e6f9ff; padding:10px 12px; border-radius:10px; margin:6px 0; }
    .bubble-ai { background:#0e1e24; color:#aff; padding:10px 12px; border-radius:10px; margin:6px 0; }
    </style>""", unsafe_allow_html=True)

def render_chat_messages(messages):
    with st.container():
        st.markdown('<div class="chat-box">', unsafe_allow_html=True)
        for msg in messages:
            sender = msg.get("sender", "")
            role = msg.get("role", "")
            content = msg.get("content", "") or ""
            image_path = msg.get("image_path", None)
            meta = f"<div class='small' style='color:#9fb8c9'>{sender}</div>"
            st.markdown(meta, unsafe_allow_html=True)
            if role == "assistant":
                st.markdown(f"<div class='bubble-ai'>{html.escape(content).replace(chr(10),'<br>')}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='bubble-user'>{html.escape(content).replace(chr(10),'<br>')}</div>", unsafe_allow_html=True)
            if image_path:
                st.image(str(image_path), width=300)
        st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# State init
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "persona" not in st.session_state:
    st.session_state.persona = "Friendly"

local_css()

# ---------------------------
# Sidebar (no login/register)
# ---------------------------
with st.sidebar:
    st.markdown("## Nexa — Assistant")
    new_user = st.text_input("Display name", st.session_state.user)
    if new_user and new_user != st.session_state.user:
        st.session_state.user = new_user

    st.markdown("---")
    st.markdown("### Conversations")
    convs = list_conversations(st.session_state.user)
    for c in convs:
        title, cid = c["title"], c["id"]
        if st.button(f"🗨 {title}", key=f"open_{cid}"):
            st.session_state.conv_id = cid
            st.rerun()
    if st.button("➕ New conversation"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()

    st.markdown("---")
    persona_choice = st.selectbox("Persona", ["Friendly","Neutral","Cheerful","Professional"],
                                  index=["Friendly","Neutral","Cheerful","Professional"].index(st.session_state.persona))
    st.session_state.persona = persona_choice

    st.markdown("---")
    st.write("**Model:**", MODEL)
    st.write("**DB:**", DB_PATH)

# ---------------------------
# Main chat area
# ---------------------------
left, right = st.columns([3, 1])
with left:
    st.markdown("### 💬 Chat")

    messages = load_messages(st.session_state.conv_id)
    render_chat_messages(messages)

    with st.form("chat_form", clear_on_submit=False):
        user_text = st.text_area("Message", key="msg", height=80, placeholder="Ask Nexa anything...")
        uploaded = st.file_uploader("Attach image", type=["png","jpg","jpeg"], key="up")
        send = st.form_submit_button("Send")
        if send:
            img_path = None
            if uploaded:
                fname = f"{st.session_state.user}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{Path(uploaded.name).suffix}"
                fpath = UPLOAD_DIR / fname
                fpath.write_bytes(uploaded.read())
                img_path = str(fpath)

            save_message(st.session_state.conv_id, st.session_state.user, "user", user_text or "", img_path)
            if user_text:
                rename_conversation_if_default(st.session_state.conv_id, simple_main_motive(user_text))

            history = load_messages(st.session_state.conv_id)
            payload = [{"role": "system", "content": f"You are Nexa, a helpful assistant. Persona: {st.session_state.persona}."}]
            for m in history:
                role = "assistant" if m["role"] == "assistant" else "user"
                payload.append({"role": role, "content": m["content"] or ""})
            payload.append({"role": "user", "content": user_text or ""})

            try:
                if OPENROUTER_API_KEY:
                    with st.spinner("Thinking..."):
                        reply = call_openrouter(payload, model=MODEL)
                else:
                    reply = f"[{st.session_state.persona}] Response to: {user_text}"
            except Exception as e:
                reply = f"(Error: {e})"

            save_message(st.session_state.conv_id, "Nexa", "assistant", reply, None)
            st.rerun()

with right:
    st.markdown("### Info")
    st.markdown(f"**User:** {st.session_state.user}")
    st.markdown(f"**Conversation ID:** {st.session_state.conv_id}")
    st.markdown(f"**Persona:** {st.session_state.persona}")
    st.markdown("---")
    st.markdown("### Tips")
    st.markdown("- Upload images to include them in chat.")
    st.markdown("- First message becomes title motive automatically.")
    st.markdown("---")
    st.markdown("### App")
    st.write("Nexa uses OpenRouter API for replies if the key is set.")

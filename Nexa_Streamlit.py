# app.py — Nexa Streamlit (OpenRouter) version
# Dark theme, gpt-3.5-turbo, simple SQLite auth
# Usage:
#   export OPENROUTER_API_KEY="your_openrouter_key"
#   pip install -r requirements.txt
#   streamlit run app.py

import os
import sqlite3
import requests
import tempfile
from datetime import datetime
from pathlib import Path
import streamlit as st

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
    # messages: list of dicts with fields sender, role, content, image_path
    container = st.container()
    with container:
        st.markdown('<div class="chat-box">', unsafe_allow_html=True)
        for m in messages:
            role = m.get("role", "user")
            sender = m.get("sender", "")
            content = m.get("content", "") or ""
            image_path = m.get("image_path", None)
            ts = m.get("timestamp", "")
            meta = f"<div class='meta'>{sender} • {ts}</div>"
            if role == "assistant":
                st.markdown(meta, unsafe_allow_html=True)
                if content:
                    st.markdown(f"<div class='bubble-ai'>{st.escape(content).replace('\\n','<br/>')}</div>", unsafe_allow_html=True)
                if image_path:
                    try:
                        st.image(str(image_path), width=360)
                    except Exception:
                        pass
            else:
                st.markdown(meta, unsafe_allow_html=True)
                if content:
                    st.markdown(f"<div class='bubble-user'>{st.escape(content).replace('\\n','<br/>')}</div>", unsafe_allow_html=True)
                if image_path:
                    try:
                        st.image(str(image_path), width=360)
                    except Exception:
                        pass
        st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Streamlit App
# ---------------------------
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")
local_css()

if "user" not in st.session_state:
    st.session_state.user = None
if "conv_id" not in st.session_state:
    st.session_state.conv_id = None
if "persona" not in st.session_state:
    st.session_state.persona = "Friendly"

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
                # create default conversation if none
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
    
                           # delete conversation (simple)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM messages WHERE conversation_id=?", (c["id"],))
        cur.execute("DELETE FROM conversations WHERE id=?", (c["id"],))
        conn.commit()
        conn.close()
        st.rerun()

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
    st.markdown("<div style='padding:30px'><h2 style='color:#dff9ff'>Welcome to Nexa</h2><p class='small'>Please login or register in the sidebar to start.</p></div>", unsafe_allow_html=True)
else:
    left_col, right_col = st.columns([3,1])
    with left_col:
        st.markdown("### Chat")
        # load messages for current conv
        if not st.session_state.conv_id:
            # create a conversation on first login if none
            st.session_state.conv_id = create_conversation(st.session_state.user)
        messages = load_messages(st.session_state.conv_id)
        render_chat_messages(messages)

        # input area
        with st.form("chat_input_form", clear_on_submit=False):
            user_text = st.text_area("Message", key="user_msg", height=80, placeholder="Ask Nexa anything...")
            uploaded_file = st.file_uploader("Attach image (optional)", type=["png","jpg","jpeg","gif"])
            submit = st.form_submit_button("Send")
            if submit:
                # Save user message (and image if present)
                img_path = None
                if uploaded_file:
                    # persist uploaded file in uploads/
                    suffix = Path(uploaded_file.name).suffix
                    fname = f"{st.session_state.user}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{suffix}"
                    fpath = UPLOAD_DIR / fname
                    bytes_data = uploaded_file.read()
                    fpath.write_bytes(bytes_data)
                    img_path = str(fpath)
                # Save user message
                save_message(st.session_state.conv_id, st.session_state.user, "user", user_text or None, img_path)
                # rename conversation title once (best effort)
                if user_text:
                    rename_conversation_if_default(st.session_state.conv_id, simple_main_motive(user_text, max_words=5))
                # prepare messages for API: include history
                history = load_messages(st.session_state.conv_id)
                payload_messages = [{"role":"system","content":f"You are Nexa, a helpful assistant. Persona: {st.session_state.persona}."}]
                for m in history:
                    role = "assistant" if m["role"] == "assistant" else "user"
                    content = m["content"] if m["content"] else ""
                    payload_messages.append({"role": role, "content": content})
                # append the new user message (redundant but safe)
                payload_messages.append({"role":"user","content": user_text or ""})

                # call OpenRouter
                assistant_reply = ""
                try:
                    with st.spinner("Thinking..."):
                        assistant_reply = call_openrouter(payload_messages, model=MODEL)
                except Exception as e:
                    assistant_reply = f"(LLM error) {e}"

              # Save assistant reply
save_message(st.session_state.conv_id, "assistant", "assistant", assistant_reply, None)
# rerender messages
st.rerun()

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
        st.markdown("This app uses OpenRouter for AI replies. Make sure `OPENROUTER_API_KEY` is set in your environment.")

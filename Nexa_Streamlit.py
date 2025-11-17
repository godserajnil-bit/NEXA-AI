# Nexa_Streamlit_fixed_v2.py
# Streamlit Nexa UI — screenshot-like layout, mic auto-write+send, New Chat behavior.
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------
# Safe UTF-8 IO
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
# Config + constants
# ---------------------------
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")
DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ---------------------------
# DB utilities (same as your original)
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def reset_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_conn()
    c = conn.cursor()
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

if not os.path.exists(DB_PATH):
    reset_db()

def create_conversation(user, title="New chat"):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (user, title, created_at) VALUES (?, ?, ?)", (user, title, now))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def list_conversations(user):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title FROM conversations WHERE user=? ORDER BY id DESC", (user,))
    rows = c.fetchall()
    conn.close()
    return rows

def load_messages(cid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    rows = c.fetchall()
    conn.close()
    return rows

def save_message(cid, sender, role, content):
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
              (cid, sender, role, content, ts))
    conn.commit()
    conn.close()

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

# ---------------------------
# LLM wrapper (OpenRouter)
# ---------------------------
def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return f"🔒 Offline mode — echo: {messages[-1].get('content','')}"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": MODEL, "messages": messages},
            headers=headers,
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0].get("message", {}).get("content", "") or ""
        return ""
    except Exception as e:
        return f"⚠️ Nexa error: {e}"

# ---------------------------
# Styling
# ---------------------------
st.markdown(
    """
    <style>
    /* (unchanged CSS — no modifications) */
    </style>
    """, unsafe_allow_html=True)

# ---------------------------
# Session setup
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# ---------------------------
# Layout
# ---------------------------
st.markdown('<div class="outer">', unsafe_allow_html=True)

# left teal
left_html = """(UNCHANGED)"""
st.markdown(left_html, unsafe_allow_html=True)

# center frame
st.markdown('<div class="center-wrap">', unsafe_allow_html=True)
st.markdown('<div class="frame">', unsafe_allow_html=True)
st.markdown('<div class="chat-shell">', unsafe_allow_html=True)

# left menu
menu_html = """(UNCHANGED)"""
st.markdown(menu_html, unsafe_allow_html=True)

# main area
st.markdown('<div class="main-area">', unsafe_allow_html=True)

messages = load_messages(st.session_state.conv_id)
has_messages = len(messages) > 0

if not has_messages:
    welcome_html = """(UNCHANGED)"""
    st.markdown(welcome_html, unsafe_allow_html=True)
else:
    st.markdown('<div class="messages">', unsafe_allow_html=True)
    for m in messages:
        role = m["role"]
        content = html.escape(m["content"] or "")
        if role == "assistant":
            st.markdown(f"<div class='msg-ai'>{content}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='msg-user'>{content}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# mic component (unchanged)
components.html("""(UNCHANGED JS)""", height=80)

# form
with st.form("nexa_input_form", clear_on_submit=True):
    user_text = st.text_input("Message", placeholder="Ask Nexa anything...", key="nexa_input")
    submitted = st.form_submit_button("Send")

components.html("""(UNCHANGED LISTENER JS)""", height=0)

st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Sidebar
# ---------------------------
with st.sidebar:
    st.markdown("## Conversations")
    st.text_input("Display name", value=st.session_state.user, key="sidename")
    st.session_state.user = st.session_state.get("sidename", st.session_state.user)

    st.markdown("---")
    convs = list_conversations(st.session_state.user)
    if convs:
        for c in convs:
            title = c["title"] or "New chat"
            if st.button(title, key=f"open_{c['id']}"):
                st.session_state.conv_id = c["id"]
                st.rerun()
    else:
        st.info("No conversations yet — press New Chat to start.")

    if st.button("➕ New Chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()

    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()

    st.checkbox("🔊 Nexa speak replies (browser TTS)", key="speak_on_reply")

# ---------------------------
# Simple commands
# ---------------------------
def handle_simple_commands_and_maybe_open(text):
    low = text.strip().lower()
    if low.startswith("open youtube"):
        components.html("<script>window.open('https://www.youtube.com','_blank');</script>", height=0)
        return "✅ Opening YouTube..."
    if low.startswith("open google"):
        components.html("<script>window.open('https://www.google.com','_blank');</script>", height=0)
        return "✅ Opening Google..."
    return None

# ---------------------------
# JS hook for New Chat
# ---------------------------
components.html("""(UNCHANGED JS)""", height=0)

# ---------------------------
# Handle message submission
# ---------------------------
if submitted and user_text and user_text.strip():
    text = user_text.strip()
    save_message(st.session_state.conv_id, st.session_state.user, "user", text)
    rename_conversation_if_default(st.session_state.conv_id, text.split("\n",1)[0][:40])

    history = load_messages(st.session_state.conv_id)
    payload = [{"role":"system","content":"You are Nexa, a helpful assistant."}]
    for m in history:
        payload.append({"role": m["role"], "content": m["content"]})

    with st.spinner("Nexa is thinking..."):
        reply = call_openrouter(payload)
    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    if st.session_state.get("speak_on_reply", False):
        safe = html.escape(reply).replace("\n", " ")
        tts = f"<script>speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));</script>"
        components.html(tts, height=0)

    st.rerun()

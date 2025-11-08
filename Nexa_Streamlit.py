# Nexa_Streamlit.py — Realistic ChatGPT-style AI (clean + fixed + top-aligned)

import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st

# ---------------------------
# UTF-8 Handling
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
# Config
# ---------------------------
st.set_page_config(page_title="Nexa", layout="wide")
DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ---------------------------
# Database Setup
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

# ---------------------------
# DB Helpers
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

def rename_conversation_if_default(cid, new_title):
    if not new_title:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (row["title"] == "New chat" or not row["title"]):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid))
        conn.commit()
    conn.close()

def save_message(cid, sender, role, content):
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
              (cid, sender, role, content, ts))
    conn.commit()
    conn.close()

# ---------------------------
# Utility
# ---------------------------
STOPWORDS = {"the","and","for","that","with","this","what","when","where","which","would","could","should",
             "your","from","have","just","like","also","been","they","them","will","how","can","you","are","its"}

def simple_main_motive(text, max_words=4):
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    words = [w for w in cleaned.split() if w not in STOPWORDS and len(w) > 2]
    if not words:
        return text[:40]
    return " ".join(words[:max_words]).capitalize()

def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return "⚠️ [Offline mode] Nexa simulated reply (no API key)."
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": MODEL, "messages": messages},
            headers=headers,
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Nexa error: {e}"

# ---------------------------
# CSS (ChatGPT Modern Style, no black background)
# ---------------------------
st.markdown("""
<style>
.stApp { background-color: #0d1117; color: #e6f6ff; }
.chat-window {
    padding: 10px;
    border-radius: 10px;
    max-height: 75vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    justify-content: flex-start; /* ✅ messages at top */
}
.msg-user {
    background: #1f6feb;
    color: white;
    padding: 10px 15px;
    border-radius: 12px;
    width: fit-content;
    margin: 6px 0 6px auto;
}
.msg-ai {
    background: #21262d;
    color: #e6f6ff;
    padding: 10px 15px;
    border-radius: 12px;
    width: fit-content;
    margin: 6px auto 6px 0;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session State
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "new_msg" not in st.session_state:
    st.session_state.new_msg = ""

# ---------------------------
# Sidebar
# ---------------------------
with st.sidebar:
    st.markdown("## 💠 Nexa")
    new_name = st.text_input("Display name", st.session_state.user)
    if new_name:
        st.session_state.user = new_name

    st.markdown("---")
    st.markdown("### 💬 Conversations")
    for conv in list_conversations(st.session_state.user):
        if st.button(conv["title"], key=f"c{conv['id']}"):
            st.session_state.conv_id = conv["id"]
            st.rerun()

    if st.button("➕ New chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()

    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()

# ---------------------------
# Chat Window
# ---------------------------
st.markdown("### 💭 Chat")
st.markdown('<div class="chat-window">', unsafe_allow_html=True)
messages = load_messages(st.session_state.conv_id)

# ✅ Messages appear from the top
for m in messages:
    if m["role"] == "assistant":
        st.markdown(f"<div class='msg-ai'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='msg-user'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# Input Bar
# ---------------------------
col1, col2 = st.columns([9, 1])
with col1:
    st.session_state.new_msg = st.text_input(
        "Type your message...",
        value=st.session_state.new_msg,
        placeholder="Ask me anything and press Enter ↵",
        label_visibility="collapsed"
    )
with col2:
    send = st.button("Send")

# ---------------------------
# Message Handling
# ---------------------------
if send and st.session_state.new_msg.strip():
    user_text = st.session_state.new_msg.strip()
    st.session_state.new_msg = ""  # ✅ Clear safely
    save_message(st.session_state.conv_id, st.session_state.user, "user", user_text)
    rename_conversation_if_default(st.session_state.conv_id, simple_main_motive(user_text))

    history = load_messages(st.session_state.conv_id)
    payload = [{"role": "system", "content": "You are Nexa, a realistic AI assistant like ChatGPT."}]
    for m in history:
        payload.append({"role": m["role"], "content": m["content"]})

    with st.spinner("Nexa is thinking..."):
        reply = call_openrouter(payload)
        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    st.rerun()

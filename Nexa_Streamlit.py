# =========================
# NEXA – STUDY ONLY AI
# Streamlit | Stable | Exam Focused | Persistent Memory
# =========================

import os, sys, io, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# -------------------------
# UTF-8 SAFE
# -------------------------
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except:
    pass

# -------------------------
# CONFIG
# -------------------------
st.set_page_config(page_title="NEXA Study AI", layout="wide")
DB_PATH = "nexa_study.db"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# -------------------------
# DATABASE
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def new_conversation():
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (created_at) VALUES (?)", (ts,))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def save_message(cid, role, content):
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
        (cid, role, content, ts)
    )
    conn.commit()
    conn.close()

def load_messages(cid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    rows = c.fetchall()
    conn.close()
    return rows

def list_conversations():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM conversations ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

# -------------------------
# STUDY-ONLY AI CALL
# -------------------------
def call_ai(history):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": history,
        "max_tokens": 500
    }
    r = requests.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        return "⚠️ NEXA is unavailable right now."
    return r.json()["choices"][0]["message"]["content"]

# -------------------------
# SESSION
# -------------------------
if "cid" not in st.session_state:
    st.session_state.cid = new_conversation()

# -------------------------
# STYLES
# -------------------------
st.markdown("""
<style>
[data-testid="stSidebar"] > div:first-child {background:#000;color:#fff}

.chat-user,.chat-ai{
  background:#111;color:#fff;padding:12px 14px;
  border-radius:14px;margin:10px 0;max-width:80%
}
.chat-user{margin-left:auto}
.chat-ai{margin-right:auto}

form[data-testid="stForm"]{
  position:fixed;bottom:10px;left:50%;
  transform:translateX(-50%);z-index:9999;
  display:flex;gap:8px
}

.block-container{padding-bottom:140px}

.mic-btn{
  background:black;color:white;
  border-radius:50%;width:46px;height:46px;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;font-size:20px
}

input[type="text"]{
  border-radius:30px;padding:12px 16px
}

form button{display:none}
</style>
""", unsafe_allow_html=True)

# -------------------------
# SIDEBAR
# -------------------------
with st.sidebar:
    st.markdown("## 📘 NEXA")
    st.markdown("Study-Only AI")

    if st.button("➕ New Chat"):
        st.session_state.cid = new_conversation()
        st.rerun()

    st.markdown("### 📚 Exam Prep")
    st.markdown("- MHT-CET")
    st.markdown("- Boards")
    st.markdown("- Numericals")
    st.markdown("- Theory")

    st.markdown("### 🕘 History Saved")
    for c in list_conversations():
        if st.button(f"Chat {c['id']}"):
            st.session_state.cid = c["id"]
            st.rerun()

# -------------------------
# CHAT DISPLAY
# -------------------------
for m in load_messages(st.session_state.cid):
    safe = html.escape(m["content"])
    if m["role"] == "assistant":
        st.markdown(f"<div class='chat-ai'>{safe}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='chat-user'>{safe}</div>", unsafe_allow_html=True)

# -------------------------
# INPUT + MIC
# -------------------------
with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input(
        "",
        placeholder="Ask a study or exam question…",
        label_visibility="collapsed"
    )

    components.html("""
    <div class="mic-btn" onclick="
      const r = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
      r.lang='en-IN';
      r.onresult=e=>{document.querySelector('input').value=e.results[0][0].transcript;}
      r.start();
    ">🎤</div>
    """, height=50)

    submitted = st.form_submit_button("")

# -------------------------
# SUBMIT LOGIC
# -------------------------
if submitted and user_input.strip():
    save_message(st.session_state.cid, "user", user_input)

    history = [{
        "role": "system",
        "content": (
            "You are NEXA, a STRICT study-only AI. "
            "Answer ONLY academic questions related to exams, syllabus, physics, chemistry, maths. "
            "If the question is not study-related, politely refuse."
        )
    }]

    for m in load_messages(st.session_state.cid):
        history.append({"role": m["role"], "content": m["content"]})

    with st.spinner("NEXA thinking…"):
        reply = call_ai(history)

    save_message(st.session_state.cid, "assistant", reply)
    st.rerun()

# =========================
# END
# =========================

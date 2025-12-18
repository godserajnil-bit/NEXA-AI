# =========================
# NEXA – MEDICAL AI (FULL FINAL CODE)
# Streamlit | Stable | No Errors | Plus-icon upload only
# =========================

import os, sys, io, sqlite3, requests, html, base64
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
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except:
    pass

# -------------------------
# CONFIG
# -------------------------
st.set_page_config(page_title="NEXA Medical AI", layout="wide")
DB_PATH = "nexa.db"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# -------------------------
# DATABASE
# -------------------------
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
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

if not os.path.exists(DB_PATH):
    reset_db()

def create_conversation(user):
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (user,created_at) VALUES (?,?)", (user, ts))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def load_messages(cid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    rows = c.fetchall()
    conn.close()
    return rows

def save_message(cid, role, content):
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute(
        "INSERT INTO messages (conversation_id,role,content,created_at) VALUES (?,?,?,?)",
        (cid, role, content, ts)
    )
    conn.commit()
    conn.close()

# -------------------------
# MEDICAL-ONLY AI
# -------------------------
def call_openrouter(messages):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": messages,
        "max_tokens": 500
    }
    r = requests.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        return "⚠️ Medical system unavailable."
    return r.json()["choices"][0]["message"]["content"]

# -------------------------
# SESSION
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = "Patient"
if "cid" not in st.session_state:
    st.session_state.cid = create_conversation(st.session_state.user)

# -------------------------
# STYLES
# -------------------------
st.markdown("""
<style>
[data-testid="stSidebar"] > div:first-child {background:#000;color:#fff}
.block-container {padding-bottom:130px}

.chat-user,.chat-ai{
  background:#000;color:#fff;padding:12px 14px;
  border-radius:14px;margin:10px 0;max-width:80%
}
.chat-user{margin-left:auto}
.chat-ai{margin-right:auto}

form[data-testid="stForm"]{
  position:fixed;bottom:6px;left:50%;
  transform:translateX(-50%);z-index:9999
}

section[data-testid="stFileUploaderDropzone"]{
  width:56px;height:56px;border-radius:50%;
  background:black;border:2px solid black;
  display:flex;align-items:center;justify-content:center
}
section[data-testid="stFileUploaderDropzone"] span,
section[data-testid="stFileUploaderDropzone"] small{display:none}
section[data-testid="stFileUploaderDropzone"]::after{
  content:"+";color:white;font-size:32px;font-weight:700
}
form[data-testid="stForm"] button{display:none}
</style>
""", unsafe_allow_html=True)

# -------------------------
# SIDEBAR
# -------------------------
with st.sidebar:
    st.markdown("## NEXA")
    st.markdown("Medical AI Assistant")
    if st.button("➕ New Medical Chat"):
        st.session_state.cid = create_conversation(st.session_state.user)
        st.rerun()
    if st.button("🧹 Reset All Data"):
        reset_db()
        st.session_state.cid = create_conversation(st.session_state.user)
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
# INPUT (PLUS ICON + TEXT)
# -------------------------
with st.form("nexa_form", clear_on_submit=True):
    uploaded_image = st.file_uploader(
        "",
        type=["png","jpg","jpeg","webp"],
        label_visibility="collapsed"
    )
    user_input = st.text_input(
        "",
        placeholder="Describe symptoms or ask a medical question…",
        label_visibility="collapsed"
    )
    submitted = st.form_submit_button("")

# -------------------------
# SUBMIT HANDLER
# -------------------------
if submitted and user_input:
    save_message(st.session_state.cid, "user", user_input)

    history = [{
        "role": "system",
        "content": (
            "You are NEXA, a strict medical AI assistant. "
            "Answer ONLY medical or health-related questions. "
            "If the query is not medical, politely refuse."
        )
    }]

    for m in load_messages(st.session_state.cid):
        history.append({"role": m["role"], "content": m["content"]})

    if uploaded_image:
        img_b64 = base64.b64encode(uploaded_image.getvalue()).decode()
        history.append({
            "role":"user",
            "content":[
                {"type":"text","text":user_input},
                {"type":"image_url","image_url":f"data:image/png;base64,{img_b64}"}
            ]
        })
    else:
        history.append({"role":"user","content":user_input})

    with st.spinner("NEXA analyzing medically…"):
        reply = call_openrouter(history)

    save_message(st.session_state.cid, "assistant", reply)
    st.rerun()

# =========================
# END OF FILE
# =========================

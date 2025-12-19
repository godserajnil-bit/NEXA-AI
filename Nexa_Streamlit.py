# =========================
# NEXA – STUDY ONLY AI (FINAL STABLE)
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
            title TEXT,
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

    c.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            exam_type TEXT,
            total_questions INTEGER,
            correct_answers INTEGER,
            percentage REAL,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

def new_conversation(title):
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (title, created_at) VALUES (?,?)", (title, ts))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def delete_conversation(cid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
    c.execute("DELETE FROM scores WHERE conversation_id=?", (cid,))
    c.execute("DELETE FROM conversations WHERE id=?", (cid,))
    conn.commit()
    conn.close()

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

def save_score(cid, exam, total_q, correct_q):
    percentage = round((correct_q / total_q) * 100, 2)
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO scores
        (conversation_id, exam_type, total_questions, correct_answers, percentage, created_at)
        VALUES (?,?,?,?,?,?)
    """, (cid, exam, total_q, correct_q, percentage, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return percentage

def load_messages(cid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    rows = c.fetchall()
    conn.close()
    return rows

def list_conversations():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title FROM conversations ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

# -------------------------
# AI CALL
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
        "max_tokens": 700
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        return "NEXA is temporarily unavailable."
    return r.json()["choices"][0]["message"]["content"]

# -------------------------
# SESSION
# -------------------------
if "cid" not in st.session_state:
    st.session_state.cid = new_conversation("General Study")
if "mode" not in st.session_state:
    st.session_state.mode = "General Study"
if "test_mode" not in st.session_state:
    st.session_state.test_mode = False
if "question_count" not in st.session_state:
    st.session_state.question_count = 0
if "correct_count" not in st.session_state:
    st.session_state.correct_count = 0
if "max_questions" not in st.session_state:
    st.session_state.max_questions = 10

# -------------------------
# STYLES
# -------------------------
st.markdown("""
<style>
[data-testid="stSidebar"] > div:first-child {background:#000;color:#fff}
.block-container{padding-bottom:160px}

.chat-wrapper{
  height:70vh;
  overflow-y:auto;
  padding-right:10px;
}

.chat-user,.chat-ai{
  background:#111;color:#fff;padding:12px 14px;
  border-radius:14px;margin:10px 0;max-width:80%
}
.chat-user{margin-left:auto}
.chat-ai{margin-right:auto}

form[data-testid="stForm"]{
  position:fixed;bottom:10px;left:50%;
  transform:translateX(-50%);
  display:flex;gap:8px;z-index:9999
}

.mic-btn{
  background:black;color:white;
  border-radius:50%;width:46px;height:46px;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;font-size:18px
}
</style>
""", unsafe_allow_html=True)

# -------------------------
# SIDEBAR
# -------------------------
with st.sidebar:
    st.markdown("## 📘 NEXA")
    st.caption("Study-Only AI")

    if st.button("➕ New Chat"):
        st.session_state.cid = new_conversation("General Study")
        st.session_state.mode = "General Study"
        st.session_state.test_mode = False
        st.session_state.question_count = 0
        st.session_state.correct_count = 0
        st.rerun()

    with st.expander("📚 Exam Prep"):
        for title in ["MHT-CET", "10th Board", "12th Board", "Class 5–9"]:
            if st.button(title):
                st.session_state.cid = new_conversation(title)
                st.session_state.mode = title
                st.session_state.test_mode = False
                st.session_state.question_count = 0
                st.session_state.correct_count = 0
                st.rerun()

    if st.button("📝 Test Mode"):
        st.session_state.test_mode = True
        st.session_state.question_count = 0
        st.session_state.correct_count = 0
        save_message(st.session_state.cid, "assistant", "Test mode ON. I will ask questions one by one.")
        st.rerun()

    st.markdown("### 🕘 History")
    for c in list_conversations():
        col1, col2 = st.columns([4,1])
        with col1:
            if st.button(c["title"], key=f"open_{c['id']}"):
                st.session_state.cid = c["id"]
                st.session_state.mode = c["title"]
                st.rerun()
        with col2:
            if st.button("❌", key=f"del_{c['id']}"):
                delete_conversation(c["id"])
                st.rerun()

# -------------------------
# CHAT DISPLAY (FIXED)
# -------------------------
st.markdown("<div class='chat-wrapper' id='chatbox'>", unsafe_allow_html=True)

for m in load_messages(st.session_state.cid):
    safe = html.escape(m["content"])
    cls = "chat-ai" if m["role"] == "assistant" else "chat-user"
    st.markdown(f"<div class='{cls}'>{safe}</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

components.html("""
<script>
const box = document.getElementById("chatbox");
if(box){ box.scrollTop = box.scrollHeight; }
</script>
""", height=0)

# -------------------------
# INPUT
# -------------------------
with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input(
        "Chat input",
        placeholder="Answer or ask…",
        label_visibility="collapsed"
    )
    components.html("""
    <div class="mic-btn" onclick="
      try{
        const r = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        r.lang='en-IN';
        r.onresult=e=>{document.querySelector('input').value=e.results[0][0].transcript;}
        r.start();
      }catch(e){}
    ">🎤</div>
    """, height=55)
    submitted = st.form_submit_button("Send")

# -------------------------
# LOGIC
# -------------------------
if submitted and user_input.strip():
    save_message(st.session_state.cid, "user", user_input)

    system_prompt = (
        f"You are NEXA conducting a test for {st.session_state.mode}. "
        "Ask ONE exam-level question. "
        "After answer, say only Correct or Incorrect and one-line reason. "
        f"Stop after {st.session_state.max_questions} questions."
    ) if st.session_state.test_mode else (
        f"You are NEXA, a strict STUDY AI for {st.session_state.mode}. "
        "Answer academically using plain text only."
    )

    history = [{"role":"system","content":system_prompt}]
    for m in load_messages(st.session_state.cid):
        history.append({"role":m["role"],"content":m["content"]})

    reply = call_ai(history)

    if st.session_state.test_mode:
        st.session_state.question_count += 1
        if "correct" in reply.lower():
            st.session_state.correct_count += 1

        if st.session_state.question_count >= st.session_state.max_questions:
            percentage = save_score(
                st.session_state.cid,
                st.session_state.mode,
                st.session_state.max_questions,
                st.session_state.correct_count
            )

            prediction = (
                "Very high chance" if percentage >= 85 else
                "Good chance" if percentage >= 70 else
                "Moderate chance" if percentage >= 55 else
                "Low chance" if percentage >= 40 else
                "Needs serious improvement"
            )

            reply += f"\n\nTest completed.\nScore: {percentage}%\nPrediction: {prediction}"
            st.session_state.test_mode = False

    save_message(st.session_state.cid, "assistant", reply)
    st.rerun()

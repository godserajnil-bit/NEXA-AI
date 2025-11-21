# Nexa_Streamlit.py
# FINAL FIXED VERSION — quote box, bottom input, black chat bubbles, stable UI

import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# -------------------- SAFE UTF-8 --------------------
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except:
    pass

# -------------------- CONFIG --------------------
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")

DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

LOGO_PATH = "/mnt/data/Screenshot (8).png"

# -------------------- DATABASE --------------------
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
    CREATE TABLE IF NOT EXISTS conversations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        sender TEXT,
        role TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()

if not os.path.exists(DB_PATH):
    reset_db()

def create_conversation(user, title="New chat"):
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations(user,title,created_at) VALUES(?,?,?)", (user, title, ts))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def list_conversations(user):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id,title FROM conversations WHERE user=? ORDER BY id DESC", (user,))
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
    c.execute(
        "INSERT INTO messages(conversation_id,sender,role,content,created_at) VALUES(?,?,?,?,?)",
        (cid, sender, role, content, ts)
    )
    conn.commit()
    conn.close()

def rename_conversation_if_default(cid, title):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (row["title"] == "New chat" or not row["title"]):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (title, cid))
        conn.commit()
    conn.close()

# -------------------- LLM --------------------
def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return f"🔒 Offline mode — {messages[-1]['content']}"

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}",
               "Content-Type": "application/json"}

    try:
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": MODEL, "messages": messages},
            headers=headers,
            timeout=60
        )
        res.raise_for_status()
        data = res.json()

        if data.get("choices"):
            return data["choices"][0]["message"]["content"]
        return "No response"

    except Exception as e:
        return f"⚠️ Error: {e}"

# -------------------- QUOTE --------------------
def get_random_quote():
    try:
        r = requests.get("https://api.quotable.io/random", timeout=5)
        if r.status_code == 200:
            j = r.json()
            return f"{j.get('content')} — {j.get('author')}"
    except:
        pass
    return "Believe in yourself and all that you are."

# -------------------- SESSION --------------------
if "user" not in st.session_state:
    st.session_state.user = "You"

if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)

if "show_intro" not in st.session_state:
    st.session_state.show_intro = True

if "intro_quote" not in st.session_state:
    st.session_state.intro_quote = get_random_quote()

# -------------------- CSS --------------------
st.markdown("""
<style>
[data-testid="stSidebar"] > div:first-child {
    background:black;
    color:white;
}

/* main background */
.block-container {
    background:#e6e6e6;
}

/* CHAT BUBBLES */
.chat-user, .chat-ai {
    background:black;
    color:white;
    padding:12px 16px;
    border-radius:20px;
    margin:10px 0;
    max-width:70%;
    font-size:16px;
}

.chat-user { margin-left:auto; }
.chat-ai { margin-right:auto; }

/* INTRO BOX */
#intro-box {
    background:#f0f0f0;
    border-radius:20px;
    padding:30px;
    text-align:center;
    width:60%;
    margin:60px auto 30px;
    box-shadow:0 10px 20px rgba(0,0,0,0.1);
}

#intro-logo {
    width:80px;
    margin-bottom:15px;
}

#intro-quote {
    font-size:18px;
    font-style:italic;
    color:#111;
}

/* INPUT BAR FIX — BOTTOM EDGE */
[data-testid="stForm"] {
    position: fixed;
    bottom: 0;
    left: 22%;
    right: 0;
    background:#e6e6e6;
    padding: 10px 20px 15px;
    border-top: 1px solid #ccc;
    z-index: 999;
}

/* Prevent covering messages */
.block-container {
    padding-bottom: 140px;
}
</style>
""", unsafe_allow_html=True)

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.header("Nexa")
    st.text_input("Your name", st.session_state.user, key="username")
    st.session_state.user = st.session_state.username

    st.subheader("Chats")
    for c in list_conversations(st.session_state.user):
        if st.button(c["title"], key=f"chat_{c['id']}"):
            st.session_state.conv_id = c["id"]
            st.session_state.show_intro = False
            st.rerun()

    if st.button("➕ New Chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.session_state.show_intro = True
        st.session_state.intro_quote = get_random_quote()
        st.rerun()

    if st.button("🧹 Reset"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.session_state.show_intro = True
        st.session_state.intro_quote = get_random_quote()
        st.rerun()

    st.checkbox("🔊 Speak Replies", key="tts")

# -------------------- INTRO SCREEN --------------------
if st.session_state.show_intro:
    st.markdown(f"""
    <div id="intro-box">
        <img id="intro-logo" src="file://{LOGO_PATH}">
        <div id="intro-quote">{html.escape(st.session_state.intro_quote)}</div>
    </div>
    """, unsafe_allow_html=True)

# -------------------- MESSAGES --------------------
for m in load_messages(st.session_state.conv_id):
    if m["role"] == "assistant":
        st.markdown(f"<div class='chat-ai'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='chat-user'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)

# -------------------- INPUT --------------------
with st.form("nexa_form", clear_on_submit=True):
    cols = st.columns([0.85, 0.15])

    with cols[0]:
        message = st.text_input("Message", placeholder="Ask Nexa...", label_visibility="collapsed")

    with cols[1]:
        sent = st.form_submit_button("Send")

# -------------------- HIDE INTRO WHEN TYPING --------------------
components.html("""
<script>
let input = parent.document.querySelector('input[type=text]');
if(input){
 input.addEventListener('input',()=>{
   let box = parent.document.getElementById('intro-box');
   if(box) box.style.display="none";
 });
}
</script>
""", height=0)

# -------------------- SEND HANDLER --------------------
if sent and message.strip():
    st.session_state.show_intro = False

    save_message(st.session_state.conv_id, st.session_state.user, "user", message)
    rename_conversation_if_default(st.session_state.conv_id, message[:40])

    history=[{"role":"system","content":"You are Nexa, a helpful assistant."}]
    for m in load_messages(st.session_state.conv_id):
        history.append({"role":m["role"],"content":m["content"]})

    with st.spinner("Nexa thinking..."):
        reply = call_openrouter(history)

    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    if st.session_state.tts:
        clean = html.escape(reply).replace("\n"," ")
        components.html(f"<script>speechSynthesis.speak(new SpeechSynthesisUtterance('{clean}'));</script>",height=0)

    st.rerun()

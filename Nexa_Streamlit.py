# Nexa_Streamlit.py
# FINAL — fixed: quote box, centered chat, new-chat behavior, DB persistence, clean UI

import sys, io, os, sqlite3, requests, html, urllib.parse
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

# -------------------- LOGO --------------------
LOCAL_LOGO_PATH = "/mnt/data/b3069378-7855-425f-a48c-24179e9d1a16.png"

if os.path.exists(LOCAL_LOGO_PATH):
    LOGO_SRC = "file://" + urllib.parse.quote(LOCAL_LOGO_PATH)
else:
    LOGO_SRC = "https://i.ibb.co/YTtR3hQ/nexa-logo.png"

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
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
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
        r = requests.get("https://api.quotable.io/random", timeout=4)
        if r.status_code == 200:
            j = r.json()
            return f"{j.get('content')} — {j.get('author')}"
    except Exception:
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
[data-testid="stSidebar"] > div:first-child { background: #000; color: #fff; }
.main .block-container { max-width: 980px; margin: 0 auto; padding-top:16px; }
.main { background: #0f1113; }
.block-container { background: transparent; padding-bottom: 150px; }

#intro-box {
  background: #f4f4f4;
  color: #111;
  border-radius: 18px;
  padding: 28px 36px;
  text-align: center;
  width: 70%;
  margin: 48px auto;
}
#intro-logo { width: 90px; display:block; margin:auto; margin-bottom:12px; }
#intro-quote { font-size:18px; font-style:italic; }

.chat-user, .chat-ai {
  background: #000;
  color: #fff;
  padding: 12px 16px;
  border-radius: 18px;
  margin: 10px 0;
  max-width: 76%;
}
.chat-user { margin-left: auto; }
.chat-ai { margin-right: auto; }

[data-testid="stForm"] {
  position: fixed;
  bottom: 0;
  left: 22%;
  right: 0;
  padding: 14px 24px;
  background: transparent;
}
</style>
""", unsafe_allow_html=True)

# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.markdown("<h2>Nexa</h2>", unsafe_allow_html=True)
    st.text_input("Your name", st.session_state.user, key="username")
    st.session_state.user = st.session_state.username

    st.markdown("---")
    st.markdown("### Chats")
    convs = list_conversations(st.session_state.user)

    for c in convs:
        if st.button(c["title"] or "New Chat", key=f"chat_{c['id']}"):
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
        st.rerun()

# -------------------- INTRO --------------------
if st.session_state.show_intro:
    st.markdown(
        f"""
        <div id="intro-box">
          <img id="intro-logo" src="{LOGO_SRC}">
          <div id="intro-quote">{html.escape(st.session_state.intro_quote)}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# -------------------- CHAT --------------------
msgs = load_messages(st.session_state.conv_id)
for m in msgs:
    content = html.escape(m["content"] or "")
    if m["role"] == "assistant":
        st.markdown(f"<div class='chat-ai'>{content}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='chat-user'>{content}</div>", unsafe_allow_html=True)

# -------------------- INPUT --------------------
with st.form("nexa_input", clear_on_submit=True):
    cols = st.columns([0.85, 0.15])
    with cols[0]:
        user_input = st.text_input("Message", placeholder="Ask Nexa...", label_visibility="collapsed")
    with cols[1]:
        send = st.form_submit_button("Send")

# Hide intro on typing
components.html("""
<script>
const input = parent.document.querySelector("input[type='text']");
if (input){
  input.addEventListener("input",()=>{
    const box = parent.document.getElementById("intro-box");
    if(box){box.style.display="none";}
  });
}
</script>
""", height=0)

# -------------------- SEND --------------------
if send and user_input.strip():
    st.session_state.show_intro = False
    save_message(st.session_state.conv_id, st.session_state.user, "user", user_input)
    rename_conversation_if_default(st.session_state.conv_id, user_input[:40])

    history = [{"role":"system","content":"You are Nexa, a helpful assistant."}]
    for m in load_messages(st.session_state.conv_id):
        history.append({"role": m["role"], "content": m["content"]})

    with st.spinner("Thinking..."):
        reply = call_openrouter(history)

    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    st.rerun()

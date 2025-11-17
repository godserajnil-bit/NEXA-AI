# Nexa Streamlit — Full UI + DB + Mic + Chat + Sidebar + Rerun (NO experimental rerun)
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

# --------------------------------------------------------
# UTF-8 I/O FIX
# --------------------------------------------------------
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except:
    pass

# --------------------------------------------------------
# CONFIG
# --------------------------------------------------------
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")

DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# --------------------------------------------------------
# DATABASE
# --------------------------------------------------------
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
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
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

def create_conversation(username, title="New chat"):
    conn = get_conn()
    c = conn.cursor()
    t = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (user, title, created_at) VALUES (?, ?, ?)", (username, title, t))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def list_conversations(username):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title FROM conversations WHERE user=? ORDER BY id DESC", (username,))
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
    t = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
              (cid, sender, role, content, t))
    conn.commit()
    conn.close()

def rename_conversation_if_default(cid, new_title):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (not row["title"] or row["title"] == "New chat"):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid))
        conn.commit()
    conn.close()

# --------------------------------------------------------
# LLM API
# --------------------------------------------------------
def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return "Offline mode — No API key"
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": MODEL, "messages": messages},
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Error: {e}"

# --------------------------------------------------------
# CSS (full, no shortcuts)
# --------------------------------------------------------
st.markdown("""
<style>

body {
    margin: 0;
    padding: 0;
    overflow-x: hidden;
}

.outer {
    display: flex;
    width: 100%;
    height: 100vh;
    overflow: hidden;
}

/* Left teal column */
.left-col {
    width: 90px;
    background: #0a8f8a;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 25px;
    gap: 25px;
    color: white;
    font-size: 28px;
    font-weight: bold;
    letter-spacing: 2px;
    border-right: 3px solid #0f7070;
}

/* Center frame border */
.center-wrap {
    width: 100%;
    height: 100%;
    background: #dbefff;
    padding: 20px;
    box-sizing: border-box;
}

.frame {
    border: 5px solid black;
    width: 100%;
    height: 100%;
    background: white;
    display: flex;
    flex-direction: row;
}

/* Chat shell */
.chat-shell {
    display: flex;
    flex-direction: row;
    width: 100%;
}

/* Sidebar inside center */
.menu-panel {
    width: 280px;
    border-right: 3px solid #cccccc;
    background: #fafafa;
    padding: 20px;
}

/* Main chat */
.main-area {
    flex: 1;
    padding: 20px;
    overflow-y: auto;
}

/* Messages */
.messages {
    width: 100%;
}

.msg-user {
    background: #c6e6ff;
    padding: 12px;
    margin: 10px 0;
    border-radius: 12px;
    max-width: 80%;
}

.msg-ai {
    background: #eee;
    padding: 12px;
    margin: 10px 0;
    border-radius: 12px;
    max-width: 80%;
}

.welcome-box {
    text-align: center;
    width: 100%;
    margin-top: 100px;
}

</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------
# SESSION INIT
# --------------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# --------------------------------------------------------
# LAYOUT START
# --------------------------------------------------------
st.markdown('<div class="outer">', unsafe_allow_html=True)

# LEFT COLUMN
st.markdown('<div class="left-col">NX</div>', unsafe_allow_html=True)

# CENTER FRAME
st.markdown('<div class="center-wrap"><div class="frame"><div class="chat-shell">', unsafe_allow_html=True)

# SIDEBAR INSIDE MAIN
st.markdown('<div class="menu-panel">', unsafe_allow_html=True)

# List chats
convs = list_conversations(st.session_state.user)
st.markdown("### Chats")

for c in convs:
    title = c["title"]
    if st.button(title, key=f"c_{c['id']}"):
        st.session_state.conv_id = c["id"]
        st.rerun()

if st.button("New Chat"):
    st.session_state.conv_id = create_conversation(st.session_state.user)
    st.rerun()

if st.button("Reset DB"):
    reset_db()
    st.session_state.conv_id = create_conversation(st.session_state.user)
    st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# MAIN AREA
st.markdown('<div class="main-area">', unsafe_allow_html=True)

messages = load_messages(st.session_state.conv_id)

if len(messages) == 0:
    st.markdown("""
        <div class="welcome-box">
            <h1>Hello, I’m Nexa 👋</h1>
            <p>Ask anything to begin.</p>
        </div>
    """, unsafe_allow_html=True)
else:
    st.markdown('<div class="messages">', unsafe_allow_html=True)
    for m in messages:
        text = html.escape(m["content"])
        if m["role"] == "assistant":
            st.markdown(f"<div class='msg-ai'>{text}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='msg-user'>{text}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------
# MIC COMPONENT
# --------------------------------------------------------
components.html("""
<script>
function startDictation() {
    if (!('webkitSpeechRecognition' in window)) {
        alert("Speech Recognition not supported");
    } else {
        var recognition = new webkitSpeechRecognition();
        recognition.lang = "en-US";
        recognition.onresult = function(event) {
            const text = event.results[0][0].transcript;
            window.parent.postMessage({type:'speech_text', data:text}, "*");
        };
        recognition.start();
    }
}
</script>
<button onclick="startDictation()" style="padding:10px;">🎤 Speak</button>
""", height=80)

# Receive mic input
components.html("""
<script>
window.addEventListener("message", (event) => {
    if (event.data.type === "speech_text") {
        const input = window.parent.document.querySelector('input[type="text"]');
        if (input) {
            input.value = event.data.data;
            input.dispatchEvent(new Event("input", { bubbles: true }));
        }
    }
});
</script>
""", height=0)

# --------------------------------------------------------
# INPUT BOX
# --------------------------------------------------------
with st.form("ask_form", clear_on_submit=True):
    user_text = st.text_input("Ask Nexa…")
    submitted = st.form_submit_button("Send")

# --------------------------------------------------------
# HANDLE CHAT INPUT
# --------------------------------------------------------
if submitted and user_text.strip():
    text = user_text.strip()

    save_message(st.session_state.conv_id, st.session_state.user, "user", text)
    rename_conversation_if_default(st.session_state.conv_id, text[:40])

    history = [{"role":"system", "content":"You are Nexa, a helpful assistant."}]
    for m in load_messages(st.session_state.conv_id):
        history.append({"role": m["role"], "content": m["content"]})

    with st.spinner("Nexa thinking..."):
        reply = call_openrouter(history)

    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)
    st.rerun()

st.markdown('</div></div></div></div></div>', unsafe_allow_html=True)

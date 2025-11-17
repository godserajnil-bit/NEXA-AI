# Nexa Streamlit — Full Working UI + Sidebar + Mic + Chat + DB
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# ------------------------------------------------------------
# UTF-8 FIX
# ------------------------------------------------------------
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except:
    pass

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")

DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------
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
    c.execute("INSERT INTO conversations (user, title, created_at) VALUES (?, ?, ?)",
              (username, title, t))
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
    c.execute("""
    INSERT INTO messages (conversation_id, sender, role, content, created_at)
    VALUES (?, ?, ?, ?, ?)""", (cid, sender, role, content, t))
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

# ------------------------------------------------------------
# API
# ------------------------------------------------------------
def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return "Offline mode — No API key"

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": MODEL, "messages": messages},
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Error: {e}"

# ------------------------------------------------------------
# STYLES
# ------------------------------------------------------------
st.markdown("""
<style>

.outer { display:flex; width:100%; height:100vh; overflow:hidden; }
.left-col {
    width:90px; background:#0a8f8a; color:white;
    display:flex; align-items:center; justify-content:center;
    font-size:30px; font-weight:bold; border-right:3px solid #0f7070;
}
.center-wrap { flex:1; background:#dbefff; padding:15px; }
.frame { border:4px solid black; height:100%; background:white; display:flex; }
.menu-panel {
    width:260px; border-right:3px solid #ccc; background:#fafafa; padding:20px; overflow-y:auto;
}
.main-area {
    flex:1; padding:20px; overflow-y:auto; height:100%;
}
.msg-user {
    background:#c6e6ff; padding:12px; margin:8px 0; border-radius:12px; max-width:80%;
}
.msg-ai {
    background:#eee; padding:12px; margin:8px 0; border-radius:12px; max-width:80%;
}
.mic-btn {
    width:40px; height:40px; border-radius:50%; font-size:20px;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# SESSION
# ------------------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)

# ------------------------------------------------------------
# MAIN LAYOUT
# ------------------------------------------------------------
st.markdown('<div class="outer">', unsafe_allow_html=True)
st.markdown('<div class="left-col">NX</div>', unsafe_allow_html=True)
st.markdown('<div class="center-wrap"><div class="frame">', unsafe_allow_html=True)

# Sidebar
st.markdown('<div class="menu-panel">', unsafe_allow_html=True)
st.markdown("### Chats")

convs = list_conversations(st.session_state.user)
for c in convs:
    if st.button(c["title"], key=f"cc_{c['id']}"):
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

# Chat Area
st.markdown('<div class="main-area">', unsafe_allow_html=True)

messages = load_messages(st.session_state.conv_id)

if not messages:
    st.markdown("<h2>Hello, I’m Nexa 👋</h2><p>Ask anything to begin.</p>", unsafe_allow_html=True)
else:
    for m in messages:
        content = html.escape(m["content"])
        if m["role"] == "assistant":
            st.markdown(f"<div class='msg-ai'>{content}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='msg-user'>{content}</div>", unsafe_allow_html=True)

# ------------------------------------------------------------
# MIC + INPUT FORM
# ------------------------------------------------------------
with st.form("nexa_main_form", clear_on_submit=True):

    cols = st.columns([0.06, 0.82, 0.12])

    # MIC
    with cols[0]:
        mic_html = """
        <button id="micBtn" class="mic-btn">🎤</button>
        <script>
        const btn = document.getElementById("micBtn");
        if (window.webkitSpeechRecognition) {
            const R = new webkitSpeechRecognition();
            R.lang = "en-US"; R.interimResults=false;
            R.onresult = e => {
                const text = e.results[0][0].transcript;
                window.parent.postMessage({type:"speech_text", text:text}, "*");
            };
            btn.onclick = ()=>{ R.start(); };
        } else {
            btn.disabled = true;
        }
        </script>
        """
        components.html(mic_html, height=60)

    # FIXED INPUT LABEL
    with cols[1]:
        user_text = st.text_input(
            "Message",
            placeholder="Ask Nexa...",
            key="nexa_input",
            label_visibility="collapsed"
        )

    # SUBMIT
    with cols[2]:
        submitted = st.form_submit_button("Send")

# Insert mic text
components.html("""
<script>
window.addEventListener("message", (e)=>{
    if(e.data.type==="speech_text"){
        const box = window.parent.document.querySelector('input[id="nexa_input"]');
        if(box){ box.value = e.data.text; box.dispatchEvent(new Event("input", {bubbles:true})); }
    }
});
</script>
""", height=0)

# ------------------------------------------------------------
# HANDLE SUBMISSION
# ------------------------------------------------------------
if submitted and user_text.strip():
    msg = user_text.strip()
    save_message(st.session_state.conv_id, st.session_state.user, "user", msg)
    rename_conversation_if_default(st.session_state.conv_id, msg[:40])

    history = [{"role": "system", "content": "You are Nexa, a helpful assistant."}]
    for m in load_messages(st.session_state.conv_id):
        history.append({"role": m["role"], "content": m["content"]})

    with st.spinner("Nexa thinking..."):
        reply = call_openrouter(history)

    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)
    st.rerun()

st.markdown('</div></div></div>', unsafe_allow_html=True)

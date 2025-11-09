# Nexa_Streamlit.py — Clean, stable, scrollable chat with mic + send + voice output

import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------
# UTF-8 Safe IO
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
    c.execute("""CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT, title TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER, sender TEXT, role TEXT, content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
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
    c.execute("INSERT INTO conversations (user, title) VALUES (?, ?)", (user, title))
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

# ---------------------------
# Simple motive finder
# ---------------------------
STOPWORDS = {"the","and","for","that","with","this","what","when","where","which","would","could","should","your","from","have","just","like","also","been","they","them","will","how","can","you","are","its"}
def simple_main_motive(text, max_words=4):
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    words = [w for w in cleaned.split() if w not in STOPWORDS and len(w) > 2]
    return " ".join(words[:max_words]).capitalize() if words else text[:40]

# ---------------------------
# Call OpenRouter
# ---------------------------
def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return "⚠️ [Offline mode] Nexa simulated reply (no API key)."
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          json={"model": MODEL, "messages": messages},
                          headers=headers, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Nexa error: {e}"

# ---------------------------
# CSS
# ---------------------------
st.markdown("""
<style>
.stApp { background-color:#0d1117; color:#e6f6ff; }
.chat-window {padding:10px; border-radius:10px; max-height:70vh; overflow-y:auto; display:flex; flex-direction:column;}
.msg-user {background:#1f6feb; color:white; padding:10px 15px; border-radius:12px; width:fit-content; margin:6px 0 6px auto;}
.msg-ai {background:#21262d; color:#e6f6ff; padding:10px 15px; border-radius:12px; width:fit-content; margin:6px auto 6px 0;}
.input-row {display:flex; gap:8px; align-items:center;}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session Init
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "typed" not in st.session_state:
    st.session_state.typed = ""
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# ---------------------------
# Sidebar
# ---------------------------
with st.sidebar:
    st.markdown("## 💠 Nexa")
    st.session_state.user = st.text_input("Display name", st.session_state.user)
    st.markdown("---")
    st.markdown("### 💬 Conversations")
    for conv in list_conversations(st.session_state.user):
        if st.button(conv["title"] or "New chat", key=f"c{conv['id']}"):
            st.session_state.conv_id = conv["id"]
            st.experimental_rerun()
    if st.button("➕ New chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.experimental_rerun()
    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.experimental_rerun()

# ---------------------------
# Chat display
# ---------------------------
st.markdown("### 💭 Chat")
st.markdown('<div class="chat-window">', unsafe_allow_html=True)
for m in load_messages(st.session_state.conv_id):
    css = "msg-ai" if m["role"] == "assistant" else "msg-user"
    st.markdown(f"<div class='{css}'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# Mic widget
# ---------------------------
mic_html = """
<div style="display:flex;gap:8px;align-items:center;">
  <button id='micStart'>🎤 Mic</button>
  <div id='micStatus' style="color:#9fb8c9;">(idle)</div>
</div>
<script>
let rec;
if (window.SpeechRecognition||window.webkitSpeechRecognition){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  rec=new SR();rec.lang='en-US';rec.continuous=true;
  rec.onresult=e=>{
    let t='';for(let i=e.resultIndex;i<e.results.length;i++){t+=e.results[i][0].transcript;}
    window.parent.postMessage({type:'transcript',text:t},'*');
  };
  micStart.onclick=()=>{rec.start();micStatus.textContent='🎙️ listening...';};
}else{micStatus.textContent='(not supported)';}
</script>
"""
components.html(mic_html, height=60)

# ---------------------------
# Input Row (text + send + speak)
# ---------------------------
c1, c2, c3 = st.columns([8, 1, 1])
with c1:
    chat_val = st.text_input("Message", st.session_state.typed, key="chat_box", placeholder="Ask me anything...")
with c2:
    send = st.button("Send")
with c3:
    speak = st.checkbox("🔊", value=st.session_state.speak_on_reply, key="speak_toggle")
    st.session_state.speak_on_reply = speak

# ---------------------------
# Handle user send
# ---------------------------
if (send or chat_val != st.session_state.typed) and chat_val.strip():
    user_text = chat_val.strip()
    save_message(st.session_state.conv_id, st.session_state.user, "user", user_text)

    # Chat context
    msgs = [{"role": "system", "content": "You are Nexa, a realistic AI assistant."}]
    for m in load_messages(st.session_state.conv_id):
        msgs.append({"role": m["role"], "content": m["content"]})
    reply = call_openrouter(msgs)
    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    # Browser TTS
    if st.session_state.speak_on_reply:
        safe = html.escape(reply).replace("\n", " ")
        components.html(f"<script>speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));</script>", height=0)

    # Reset text safely (no mutation error)
    st.session_state.typed = ""
    st.session_state["chat_box"] = ""
    st.experimental_rerun()
else:
    st.session_state.typed = chat_val

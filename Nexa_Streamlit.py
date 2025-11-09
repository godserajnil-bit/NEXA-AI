# Nexa_Streamlit.py — Stable final with chat pinned bottom + no experimental_rerun
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# UTF-8 safety
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("LANG", "en_US.UTF-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# Config
st.set_page_config(page_title="Nexa", layout="wide")
DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Database helpers
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

# Simple motive finder
STOPWORDS = {"the","and","for","that","with","this","what","when","where","which","would","could","should",
             "your","from","have","just","like","also","been","they","them","will","how","can","you","are","its"}
def simple_main_motive(text, max_words=4):
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    words = [w for w in cleaned.split() if w not in STOPWORDS and len(w) > 2]
    return " ".join(words[:max_words]).capitalize() if words else text[:40]

# Call OpenRouter
def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return "⚠️ [Offline mode] Nexa simulated reply."
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          json={"model": MODEL, "messages": messages},
                          headers=headers, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Nexa error: {e}"

# Styling
st.markdown("""
<style>
.stApp { background-color:#0d1117; color:#e6f6ff; }
.chat-window {padding:12px; border-radius:10px; max-height:65vh; overflow-y:auto; background:rgba(255,255,255,0.03);}
.msg-user {background:#1f6feb; color:white; padding:10px 14px; border-radius:12px; width:fit-content; margin:6px 0 6px auto;}
.msg-ai {background:#21262d; color:#e6f6ff; padding:10px 14px; border-radius:12px; width:fit-content; margin:6px auto 6px 0;}
.input-row {display:flex; gap:8px; align-items:center; margin-top:10px;}
.center-col {display:flex; justify-content:center;}
.chat-box {width:100%; max-width:900px;}
</style>
""", unsafe_allow_html=True)

# Session init
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "typed" not in st.session_state:
    st.session_state.typed = ""
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# Sidebar
with st.sidebar:
    st.markdown("## 💠 Nexa")
    st.session_state.user = st.text_input("Display name", st.session_state.user)
    st.markdown("---")
    st.markdown("### 💬 Conversations")
    for conv in list_conversations(st.session_state.user):
        if st.button(conv["title"] or "New chat", key=f"c{conv['id']}"):
            st.session_state.conv_id = conv["id"]
            st.rerun()
    if st.button("➕ New chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()
    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.rerun()
    st.markdown("---")
    st.session_state.speak_on_reply = st.checkbox("🔊 Speak replies", value=st.session_state.speak_on_reply)

# Main layout
col_left, col_mid, col_right = st.columns([1, 2, 1])
with col_mid:
    st.markdown('<div class="chat-box">', unsafe_allow_html=True)
    st.markdown("### 💭 Chat")
    st.markdown('<div class="chat-window" id="chat-window">', unsafe_allow_html=True)
    for m in load_messages(st.session_state.conv_id):
        css = "msg-ai" if m["role"] == "assistant" else "msg-user"
        st.markdown(f"<div class='{css}'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# Input row form
mic_html = """
<script>
(function(){
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!SpeechRecognition) return;
  const rec = new SpeechRecognition();
  rec.lang='en-US'; rec.continuous=false; rec.interimResults=false;
  let btn = document.getElementById('mic-btn');
  if(!btn) return;
  btn.onclick=()=>{
    if(btn.dataset.listening==='1'){rec.stop();return;}
    btn.dataset.listening='1'; btn.textContent='🛑';
    rec.start(); setTimeout(()=>{rec.stop();},6000);
  };
  rec.onresult=(e)=>{
    const transcript=e.results[0][0].transcript;
    const input=document.querySelector('input[data-testid="stTextInput-input"]');
    if(input){input.value=transcript;input.dispatchEvent(new Event('input',{bubbles:true}));}
  };
  rec.onend=()=>{btn.dataset.listening='0';btn.textContent='🎤';};
})();
</script>
"""

with col_mid:
    with st.form("chat_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([8, 1, 1])
        chat_val = c1.text_input("", value=st.session_state.typed, key="chat_box", placeholder="Type your message...")
        c2.markdown('<button id="mic-btn" style="padding:6px 10px;border-radius:6px;background:#0f1720;color:#9fb8c9;border:1px solid #243240;cursor:pointer;">🎤</button>', unsafe_allow_html=True)
        send = c3.form_submit_button("Send")
    components.html(mic_html, height=0)

if send and chat_val.strip():
    user_text = chat_val.strip()
    save_message(st.session_state.conv_id, st.session_state.user, "user", user_text)
    msgs = [{"role": "system", "content": "You are Nexa, a realistic AI assistant."}]
    for m in load_messages(st.session_state.conv_id):
        msgs.append({"role": m["role"], "content": m["content"]})
    with st.spinner("Nexa is thinking..."):
        reply = call_openrouter(msgs)
    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    if st.session_state.speak_on_reply:
        safe = html.escape(reply).replace("\n", " ")
        components.html(f"<script>speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));</script>", height=0)

    st.session_state.typed = chat_val  # preserve
    st.rerun()
else:
    st.session_state.typed = chat_val or st.session_state.typed

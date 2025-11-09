# Nexa_Streamlit.py — Final Stable Build
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
.chat-window {
    padding:10px; border-radius:10px;
    max-height:80vh; overflow-y:auto;
    display:flex; flex-direction:column; justify-content:flex-end;
}
.msg-user {
    background:#1f6feb; color:white;
    padding:10px 15px; border-radius:12px;
    width:fit-content; margin:6px 0 6px auto;
}
.msg-ai {
    background:#21262d; color:#e6f6ff;
    padding:10px 15px; border-radius:12px;
    width:fit-content; margin:6px auto 6px 0;
}
.input-row {
    display:flex; gap:8px; align-items:center;
    justify-content:center;
}
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
            st.rerun()
    if st.button("➕ New chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()
    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.rerun()

# ---------------------------
# Chat Display
# ---------------------------
st.markdown('<div class="chat-window">', unsafe_allow_html=True)
for m in load_messages(st.session_state.conv_id):
    css = "msg-ai" if m["role"] == "assistant" else "msg-user"
    st.markdown(f"<div class='{css}'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# Input Row (chat + mic + send)
# ---------------------------
st.markdown("<br>", unsafe_allow_html=True)
col_mid = st.container()
with col_mid:
    with st.form("chat_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([10, 1, 1])
        chat_val = c1.text_input("", value=st.session_state.typed, key="chat_box", placeholder="Type your message...")
        mic_html = """
        <script>
        let rec;
        if (window.SpeechRecognition||window.webkitSpeechRecognition){
          const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
          rec=new SR();rec.lang='en-US';rec.continuous=false;rec.interimResults=false;
          rec.onresult=e=>{
            let text=e.results[0][0].transcript;
            window.parent.postMessage({type:'transcript',text:text},'*');
          };
          rec.onend=()=>{document.getElementById('mic-btn').innerHTML='🎤';};
        }
        window.addEventListener('message', (e)=>{
          if(e.data && e.data.type==='transcript'){
            const input=document.querySelector('input[data-testid="stTextInput-input"]');
            if(input){input.value=e.data.text;input.dispatchEvent(new Event('input',{bubbles:true}));}
          }
        });
        function startMic(){
          if(rec){rec.start();document.getElementById('mic-btn').innerText='🛑';setTimeout(()=>{rec.stop();},6000);}
        }
        </script>
        <button id="mic-btn" onclick="startMic()" style="padding:6px 10px;border-radius:6px;background:#0f1720;color:#9fb8c9;border:1px solid #243240;cursor:pointer;">🎤</button>
        """
        c2.markdown(mic_html, unsafe_allow_html=True)
        send = c3.form_submit_button("Send")

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

    st.session_state.typed = ""
    st.rerun()
else:
    st.session_state.typed = chat_val or st.session_state.typed

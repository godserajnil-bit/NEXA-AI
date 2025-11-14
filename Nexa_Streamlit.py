# Nexa_Streamlit_fixed.py
# Simple Nexa UI with working mic (auto-write + auto-send) and proper New Chat refresh.

import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

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
# Config + constants
# ---------------------------
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")
DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ---------------------------
# DB utilities
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            sender TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

if not os.path.exists(DB_PATH):
    reset_db()

def create_conversation(user, title="New chat"):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (user, title, created_at) VALUES (?, ?, ?)", (user, title, now))
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

def rename_conversation_if_default(cid, new_title):
    if not new_title:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (not row["title"] or row["title"] == "New chat"):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid))
        conn.commit()
    conn.close()

# ---------------------------
# LLM wrapper (OpenRouter)
# ---------------------------
def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return f"🔒 Offline mode — echo: {messages[-1].get('content','')}"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": MODEL, "messages": messages},
            headers=headers,
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0].get("message", {}).get("content", "") or ""
        return ""
    except Exception as e:
        return f"⚠️ Nexa error: {e}"

# ---------------------------
# Styling (simple, centered chat)
# ---------------------------
st.markdown("""
<style>
.stApp { background:#0d1117; color:#e6f6ff; }
.left-panel { padding: 12px; }
.brand { font-size:22px; font-weight:700; color:#1f6feb; margin-bottom:8px; }
.chat-area { display:flex; justify-content:center; }
.chat-window {
    width: 720px;
    background: rgba(255,255,255,0.02);
    padding: 14px;
    border-radius: 12px;
    max-height: 70vh;
    overflow-y: auto;
    box-shadow: 0 6px 18px rgba(0,0,0,0.6);
}
.msg-user { background:#1f6feb; color:#fff; padding:10px 14px; border-radius:12px; margin:8px 0; max-width:80%; margin-left:auto;}
.msg-ai { background:#111827; color:#e6f6ff; padding:10px 14px; border-radius:12px; margin:8px 0; max-width:80%; margin-right:auto;}
.small-muted { color:#9fb8c9; font-size:13px; margin-top:8px; }
.mic-btn { padding:8px 10px; border-radius:8px; background:#0b1220; color:#9fb8c9; border:1px solid #243240; cursor:pointer; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session setup
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# ---------------------------
# Sidebar (conversation history)
# ---------------------------
with st.sidebar:
    st.markdown('<div class="left-panel">', unsafe_allow_html=True)
    st.markdown('<div class="brand">Nexa</div>', unsafe_allow_html=True)
    st.text_input("Display name", value=st.session_state.user, key="sidename")
    st.session_state.user = st.session_state.get("sidename", st.session_state.user)
    st.markdown("---")
    st.markdown("### Conversations")

    convs = list_conversations(st.session_state.user)
    if convs:
        for c in convs:
            title = c["title"] or "New chat"
            if st.button(title, key=f"open_{c['id']}"):
                st.session_state.conv_id = c["id"]
                # no forced rerun; Streamlit will refresh on next interaction
    else:
        st.info("No conversations yet — press New Chat to start.")

    # ✅ FIXED: new chat instantly opens properly
    if st.button("➕ New Chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        # no forced rerun

    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
        # no forced rerun

    st.markdown("---")
    st.checkbox("🔊 Nexa speak replies (browser TTS)", key="speak_on_reply")
    st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# Chat window (center)
# ---------------------------
st.markdown('<div class="chat-area"><div class="chat-window" id="chatwin">', unsafe_allow_html=True)

messages = load_messages(st.session_state.conv_id)
if not messages:
    st.markdown("<div class='small-muted'>Start the conversation — type or use mic 🎤.</div>", unsafe_allow_html=True)
for m in messages:
    role = m["role"]
    content = html.escape(m["content"] or "")
    if role == "assistant":
        st.markdown(f"<div class='msg-ai'>{content}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='msg-user'>{content}</div>", unsafe_allow_html=True)

st.markdown('</div></div>', unsafe_allow_html=True)

# ---------------------------
# Mic HTML (auto-write + auto-send FIXED)
# ---------------------------
mic_component = r"""
<div style="display:flex;gap:8px;align-items:center;">
  <button id="micLocal" class="mic-btn">🎤</button>
  <div id="micStatus" style="color:#9fb8c9;font-size:13px;">(click to speak)</div>
</div>
<script>
(function(){
  const btn=document.getElementById('micLocal');
  const status=document.getElementById('micStatus');
  if(!window.SpeechRecognition && !window.webkitSpeechRecognition){
    status.innerText="(speech not supported)";
    btn.disabled=true;
    return;
  }
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  const rec=new SR();
  rec.lang='en-US'; rec.interimResults=false; rec.maxAlternatives=1;
  rec.onstart=()=>{status.innerText="(listening...)";btn.innerText="🛑";};
  rec.onend=()=>{status.innerText="(stopped)";btn.innerText="🎤";};
  rec.onerror=e=>{status.innerText="(error) "+e.error;btn.innerText="🎤";};
  rec.onresult=e=>{
    const text=e.results[0][0].transcript;
    window.parent.postMessage({type:'nexa_transcript', text:text}, '*');
  };
  btn.onclick=()=>{try{rec.start();setTimeout(()=>{try{rec.stop();}catch(e){}},6000);}catch(e){}};
})();
</script>
"""
components.html(mic_component, height=80)

# ---------------------------
# Input area + auto mic listener (100% fixed)
# ---------------------------
with st.form("nexa_input_form", clear_on_submit=True):
    user_text = st.text_input("Message", placeholder="Ask Nexa anything...", key="nexa_input")
    submitted = st.form_submit_button("Send")

# ---------------------------
# JS listener — robust insertion + click
# ---------------------------
js_listener = r"""
<script>
window.addEventListener('message', (ev)=>{
  try{
    if(!ev.data || ev.data.type!=='nexa_transcript') return;
    const text = ev.data.text || '';

    // try a few selectors (works across Streamlit versions + mobile)
    let input = document.querySelector('input[data-testid="stTextInput-input"]')
             || document.querySelector('input[data-baseweb="input"]')
             || document.querySelector('input[type="text"]')
             || document.querySelector('input[role="textbox"]')
             || document.querySelector('input');

    if(!input){
      console.warn('Nexa: input not found for transcript');
      return;
    }

    // set value and trigger input event
    input.focus();
    input.value = text;
    input.dispatchEvent(new Event('input', {bubbles:true}));

    // find a "Send" button in same form or globally
    const candidateButtons = Array.from(document.querySelectorAll('button'));
    let sendBtn = candidateButtons.find(b => /^\s*send\s*$/i.test(b.innerText || ''));
    if(!sendBtn){
      // fallback: pick button with aria-label or title containing 'send'
      sendBtn = candidateButtons.find(b => /send/i.test(b.getAttribute('aria-label') || '') || /send/i.test(b.title || ''));
    }
    if(sendBtn){
      setTimeout(()=>sendBtn.click(), 200);
    }
  }catch(e){
    console.error('Nexa listener error', e);
  }
});
</script>
"""
components.html(js_listener, height=0)

# ---------------------------
# simple commands: open youtube/google
# ---------------------------
def handle_simple_commands_and_maybe_open(text):
    low = text.strip().lower()
    if low.startswith("open youtube"):
        components.html("<script>window.open('https://www.youtube.com','_blank');</script>", height=0)
        return "✅ Opening YouTube..."
    if low.startswith("open google"):
        components.html("<script>window.open('https://www.google.com','_blank');</script>", height=0)
        return "✅ Opening Google..."
    return None

# ---------------------------
# Handle message submission
# ---------------------------
if submitted and user_text and user_text.strip():
    text = user_text.strip()
    save_message(st.session_state.conv_id, st.session_state.user, "user", text)
    rename_conversation_if_default(st.session_state.conv_id, text.split("\n",1)[0][:40])

    # handle simple commands before calling LLM
    cmd_reply = handle_simple_commands_and_maybe_open(text)
    if cmd_reply is not None:
        save_message(st.session_state.conv_id, "Nexa", "assistant", cmd_reply)
        if st.session_state.get("speak_on_reply", False):
            safe = html.escape(cmd_reply).replace("\n"," ")
            components.html(f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));}}catch(e){{}}</script>", height=0)
    else:
        history = load_messages(st.session_state.conv_id)
        payload = [{"role":"system","content":"You are Nexa, a helpful assistant."}]
        for m in history:
            role = "assistant" if m["role"] == "assistant" else "user"
            payload.append({"role": role, "content": m["content"]})

        with st.spinner("Nexa is thinking..."):
            reply = call_openrouter(payload)
        save_message(st.session_state.conv_id,"Nexa","assistant",reply)

        if st.session_state.get("speak_on_reply", False):
            safe = html.escape(reply).replace("\n"," ")
            components.html(f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));}}catch(e){{}}</script>", height=0)

# End of file

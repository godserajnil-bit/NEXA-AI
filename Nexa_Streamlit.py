# Nexa_Streamlit.py
# Realistic simple Nexa UI with history, mic, Enter-to-send, and browser TTS (no pyttsx3)

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
        # deterministic offline response for testing
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
st.markdown(
    """
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
    .input-row { display:flex; gap:8px; margin-top:12px; align-items:center; justify-content:space-between; }
    .mic-btn { padding:8px 10px; border-radius:8px; background:#0b1220; color:#9fb8c9; border:1px solid #243240; cursor:pointer; }
    .send-btn { padding:8px 12px; border-radius:8px; background:#1f6feb; color:#fff; border:none; cursor:pointer; }
    .small-muted { color:#9fb8c9; font-size:13px; margin-top:8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Session state defaults
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# ---------------------------
# Left sidebar (history + controls)
# ---------------------------
with st.sidebar:
    st.markdown('<div class="left-panel">', unsafe_allow_html=True)
    st.markdown('<div class="brand">Nexa</div>', unsafe_allow_html=True)
    st.text_input("Display name", value=st.session_state.user, key="sidename")
    # keep session user in sync
    st.session_state.user = st.session_state.get("sidename", st.session_state.user)

    st.markdown("---")
    st.markdown("### Conversations")
    convs = list_conversations(st.session_state.user)
    if convs:
        for c in convs:
            title = c["title"] or "New chat"
            if st.button(title, key=f"open_{c['id']}"):
                st.session_state.conv_id = c["id"]
                # avoid experimental_rerun compatibility issues: use rerun() if present otherwise refresh page
                try:
                    st.experimental_rerun()
                except Exception:
                    # fallback: reload page by setting a dummy query param
                    st.experimental_set_query_params(_refresh=str(datetime.utcnow().timestamp()))
    else:
        st.info("No conversations yet — press New Chat to start.")

    if st.button("➕ New Chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        try:
            st.experimental_rerun()
        except Exception:
            st.experimental_set_query_params(_refresh=str(datetime.utcnow().timestamp()))

    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
        try:
            st.experimental_rerun()
        except Exception:
            st.experimental_set_query_params(_refresh=str(datetime.utcnow().timestamp()))

    st.markdown("---")
    st.checkbox("🔊 Nexa speak replies (browser TTS)", key="speak_on_reply")
    st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# Main chat area (centered)
# ---------------------------
st.markdown('<div class="chat-area">', unsafe_allow_html=True)
st.markdown('<div class="chat-window" id="chatwin">', unsafe_allow_html=True)

messages = load_messages(st.session_state.conv_id)
if not messages:
    st.markdown("<div class='small-muted'>Start the conversation — type below and press Enter or Send.</div>", unsafe_allow_html=True)

for m in messages:
    role = m["role"]
    content = html.escape(m["content"] or "")
    if role == "assistant":
        st.markdown(f"<div class='msg-ai'>{content}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='msg-user'>{content}</div>", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Mic component HTML
# ---------------------------
# This HTML provides a mic button that uses the browser SpeechRecognition API.
# When it captures a phrase it posts a message to the parent window with {type:'transcript', text: '...'}
mic_component = r"""
<div style="display:flex; gap:8px; align-items:center;">
  <button id="micLocal" class="mic-btn">🎤</button>
  <div id="micStatus" style="color:#9fb8c9; font-size:13px;">(click to speak)</div>
</div>

<script>
(function(){
  const btn = document.getElementById('micLocal');
  const status = document.getElementById('micStatus');
  let recognition = null;
  if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
    status.innerText = "(speech not supported)";
    btn.disabled = true;
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.continuous = false;

  recognition.onstart = () => {
    status.innerText = "(listening...)";
    btn.innerText = "🛑";
  };
  recognition.onerror = (e) => {
    status.innerText = "(error) " + e.error;
    btn.innerText = "🎤";
  };
  recognition.onend = () => {
    status.innerText = "(stopped)";
    btn.innerText = "🎤";
  };

  recognition.onresult = (evt) => {
    const text = evt.results[0][0].transcript;
    // Auto fill Streamlit input and auto submit
    const input = window.parent.document.querySelector('input[data-baseweb="input"]') 
               || window.parent.document.querySelector('input[data-testid="stTextInput-input"]') 
               || window.parent.document.querySelector('input[role="textbox"]');
    if (input) {
      input.focus();
      input.value = text;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      // Auto click Send button
      const buttons = Array.from(window.parent.document.querySelectorAll('button'));
      const sendBtn = buttons.find(b => /send/i.test(b.innerText));
      if (sendBtn) sendBtn.click();
    }
  };

  btn.addEventListener('click', () => {
    if (!recognition) return;
    try {
      recognition.start();
      // Auto stop after 7 seconds
      setTimeout(()=>{ try{ recognition.stop(); } catch(e){} }, 7000);
    } catch(e) {}
  });
})();
</script>
"""

# Render mic component (this will be an iframe that can postMessage to parent)
components.html(mic_component, height=80)

# ---------------------------
# Input form (uses st.form to allow Enter-to-submit and clear_on_submit)
# ---------------------------
with st.form("nexa_input_form", clear_on_submit=True):
    cols = st.columns([10, 1])
    user_text = cols[0].text_input("Message", placeholder="Ask Nexa anything and press Enter ↵", key="nexa_input")
    submit = cols[1].form_submit_button("Send")

    # When form is submitted (Enter or Send), this block will run after the `with` context ends
# (form submission handling below)

# ---------------------------
# Listen for mic transcript messages from components.html
# ---------------------------
# The following JS listener is injected once — it listens for postMessage events from the mic iframe
# and programmatically fills the Streamlit text_input and clicks Send (works in same-origin contexts).
js_listener = r"""
<script>
window.addEventListener('message', (ev) => {
  try {
    if (!ev.data) return;
    if (ev.data.type === 'nexa_transcript') {
      const text = ev.data.text || '';
      // find the text input created by Streamlit (best-effort selectors)
      const input = document.querySelector('input[data-baseweb="input"]') || document.querySelector('input[data-testid="stTextInput-input"]') || document.querySelector('input[role="textbox"]');
      if (input) {
        input.focus();
        input.value = text;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        // try to find the Send button in the same form and click it
        const buttons = Array.from(document.querySelectorAll('button'));
        const sendBtn = buttons.find(b => /send/i.test(b.innerText));
        if (sendBtn) {
          sendBtn.click();
        }
      } else {
        // fallback: copy to clipboard and notify user
        navigator.clipboard && navigator.clipboard.writeText(text);
        alert('Transcript copied to clipboard — paste into the input and press Send.');
      }
    }
  } catch(e) {
    console.error('mic msg handling error', e);
  }
});
</script>
"""
components.html(js_listener, height=0)

# ---------------------------
# Handle form submission (Enter or Send)
# ---------------------------
if submit and user_text and user_text.strip():
    content = user_text.strip()
    # save user message
    save_message(st.session_state.conv_id, st.session_state.user, "user", content)
    # rename convo if default
    rename_conversation_if_default(st.session_state.conv_id, content.split("\n", 1)[0][:40])
    # build history for LLM
    history = load_messages(st.session_state.conv_id)
    payload = [{"role":"system", "content":"You are Nexa, a helpful assistant."}]
    for m in history:
        role = "assistant" if m["role"] == "assistant" else "user"
        payload.append({"role": role, "content": m["content"]})
    # call LLM (may block briefly)
    with st.spinner("Nexa is thinking..."):
        reply = call_openrouter(payload)
    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    # Browser TTS if enabled
    if st.session_state.get("speak_on_reply", False):
        safe_reply = html.escape(reply).replace("\n", " ")
        tts_script = f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe_reply}'));}}catch(e){{console.error(e);}}</script>"
        components.html(tts_script, height=0)

    # refresh UI to show new messages (use experimental_rerun if available; fallback to setting a query param)
    try:
        st.experimental_rerun()
    except Exception:
        st.experimental_set_query_params(_refresh=str(datetime.utcnow().timestamp()))

# End of file

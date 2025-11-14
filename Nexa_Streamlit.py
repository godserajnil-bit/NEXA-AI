# Nexa_Streamlit.py
# Realistic simple Nexa UI with history, mic (auto-write + auto-send), Enter-to-send, browser TTS,
# and small commands ("open youtube", "open google").
# Keep original DB layout and behavior; minimal safe changes only.

import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

# ---------------------------
# UTF-8 Safe IO (no-op safe)
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
# DB utilities (unchanged semantics)
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
# LLM wrapper (OpenRouter) + small command handling
# ---------------------------
def call_openrouter(messages):
    # If OPENROUTER_API_KEY isn't set, return offline echo for testing
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
        # safe extraction
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0].get("message", {}).get("content", "") or ""
        return ""
    except Exception as e:
        return f"⚠️ Nexa error: {e}"

# ---------------------------
# Styling (minimal changes)
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
    .small-muted { color:#9fb8c9; font-size:13px; margin-top:8px; }
    .mic-btn { padding:8px 10px; border-radius:8px; background:#0b1220; color:#9fb8c9; border:1px solid #243240; cursor:pointer; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Session defaults
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# ---------------------------
# Sidebar (history + controls)
# ---------------------------
with st.sidebar:
    st.markdown('<div class="left-panel">', unsafe_allow_html=True)
    st.markdown('<div class="brand">Nexa</div>', unsafe_allow_html=True)
    # display name input (keeps session in sync)
    st.text_input("Display name", value=st.session_state.user, key="sidename")
    st.session_state.user = st.session_state.get("sidename", st.session_state.user)

    st.markdown("---")
    st.markdown("### Conversations")
    convs = list_conversations(st.session_state.user)
    if convs:
        for c in convs:
            title = c["title"] or "New chat"
            # clicking a button sets conv_id and redraws below naturally within same run
            if st.button(title, key=f"open_{c['id']}"):
                st.session_state.conv_id = c["id"]
    else:
        st.info("No conversations yet — press New Chat to start.")

    if st.button("➕ New Chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)

    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)

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
    st.markdown("<div class='small-muted'>Start the conversation — type below or press the mic 🎤.</div>", unsafe_allow_html=True)

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
# Mic component (sends recognized text to parent window)
# ---------------------------
mic_component = r"""
<div style="display:flex; gap:8px; align-items:center;">
  <button id="micLocal" class="mic-btn">🎤</button>
  <div id="micStatus" style="color:#9fb8c9; font-size:13px;">(Click to speak)</div>
</div>

<script>
(function(){
  const btn = document.getElementById('micLocal');
  const status = document.getElementById('micStatus');
  let recognition = null;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    status.innerText = "(speech not supported)";
    btn.disabled = true;
    return;
  }
  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.continuous = false;

  recognition.onstart = () => { status.innerText = "(listening...)"; btn.innerText = "🛑"; btn.style.background="#ff4444"; };
  recognition.onerror = (e) => { status.innerText = "(error: " + e.error + ")"; btn.innerText = "🎤"; btn.style.background=""; };
  recognition.onend = () => { status.innerText = "(stopped)"; btn.innerText = "🎤"; btn.style.background=""; };
  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript;
    // send transcript to parent
    window.parent.postMessage({ type: 'nexa_transcript', text: text }, '*');
  };

  btn.addEventListener('click', () => {
    try {
      recognition.start();
      // safety stop after 7s
      setTimeout(()=>{ try{ recognition.stop(); } catch(e){} }, 7000);
    } catch(e) { console.error(e); }
  });
})();
</script>
"""
components.html(mic_component, height=90)

# ---------------------------
# Input: form with clear_on_submit -> Enter-to-send + clears input safely
# ---------------------------
with st.form("nexa_input_form", clear_on_submit=True):
    cols = st.columns([10, 1])
    user_text = cols[0].text_input("Message", placeholder="Ask Nexa anything and press Enter ↵", key="nexa_input")
    submitted = cols[1].form_submit_button("Send")

# ---------------------------
# JS listener: receives transcript from mic iframe and writes it to the Streamlit input,
# then clicks the Send button. This is separate from the mic component.
# ---------------------------
js_listener = r"""
<script>
window.addEventListener('message', (ev) => {
  try {
    if (!ev.data || ev.data.type !== 'nexa_transcript') return;
    const text = ev.data.text || '';

    // NEW universal Streamlit selector (works on laptop + mobile)
    const input = document.querySelector('input[type="text"]') ||
                  document.querySelector('input[role="textbox"]') ||
                  document.querySelector('input');

    if (input) {
      input.focus();
      input.value = text;

      // Force Streamlit to register Vue/React input event
      input.dispatchEvent(new Event('input', { bubbles: true }));

      // Find Send button
      const buttons = Array.from(document.querySelectorAll("button"));
      const sendBtn =
        buttons.find(b => b.innerText.trim().toLowerCase() === "send");

      if (sendBtn) {
        setTimeout(() => sendBtn.click(), 200);
      }
    } else {
      alert("Mic recognized: " + text + "\\nbut input not found.");
    }

  } catch (e) {
    console.error("listener error", e);
  }
});
</script>
"""
components.html(js_listener, height=0)

# ---------------------------
# Handle special simple commands before calling LLM
# Examples:
#   - "open youtube" will open youtube.com in a new tab
#   - "open google" will open google.com in a new tab
# We'll inject a tiny JS opener if those commands are detected.
# ---------------------------
def handle_simple_commands_and_maybe_open(text):
    low = text.strip().lower()
    if low.startswith("open youtube"):
        # instruct client to open
        js = "<script>window.open('https://www.youtube.com','_blank');</script>"
        components.html(js, height=0)
        return "✅ Opening YouTube..."
    if low.startswith("open google"):
        js = "<script>window.open('https://www.google.com','_blank');</script>"
        components.html(js, height=0)
        return "✅ Opening Google..."
    return None

# ---------------------------
# Handle submission (form submit or mic auto-submission)
# ---------------------------
if submitted and user_text and user_text.strip():
    text = user_text.strip()

    # Save user message right away
    save_message(st.session_state.conv_id, st.session_state.user, "user", text)
    rename_conversation_if_default(st.session_state.conv_id, text.split("\n", 1)[0][:40])

    # handle small commands first
    cmd_reply = handle_simple_commands_and_maybe_open(text)
    if cmd_reply is not None:
        # Save command reply as Nexa assistant message
        save_message(st.session_state.conv_id, "Nexa", "assistant", cmd_reply)
        # optionally TTS
        if st.session_state.get("speak_on_reply", False):
            safe = html.escape(cmd_reply).replace("\n", " ")
            components.html(f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));}}catch(e){{}}</script>", height=0)
        # do not call LLM for this case
    else:
        # Build payload for LLM
        history = load_messages(st.session_state.conv_id)
        payload = [{"role": "system", "content": "You are Nexa, a helpful assistant."}]
        # Copy DB roles into model roles: assume rows use 'assistant' for Nexa and otherwise are user messages.
        for m in history:
            role = "assistant" if m["role"] == "assistant" else "user"
            payload.append({"role": role, "content": m["content"]})

        # call the LLM
        with st.spinner("Nexa is thinking..."):
            reply = call_openrouter(payload)

        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

        # Browser TTS if enabled
        if st.session_state.get("speak_on_reply", False):
            safe_reply = html.escape(reply).replace("\n", " ")
            tts_script = f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe_reply}'));}}catch(e){{}}</script>"
            components.html(tts_script, height=0)

    # Form has clear_on_submit=True so the input field is cleared automatically.
    # After submit we don't call experimental_rerun; Streamlit will refresh UI naturally on next run.

# End of file

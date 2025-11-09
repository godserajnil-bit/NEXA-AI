# Nexa_Streamlit.py — Realistic ChatGPT-style AI (clean + stable + browser TTS + mic widget)
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------
# UTF-8 Handling (safe)
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

# ---------------------------
# DB Helpers
# ---------------------------
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

def rename_conversation_if_default(cid, new_title):
    if not new_title:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (row["title"] == "New chat" or not row["title"]):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid))
        conn.commit()
    conn.close()

def save_message(cid, sender, role, content):
    conn = get_conn()
    c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
              (cid, sender, role, content, ts))
    conn.commit()
    conn.close()

# ---------------------------
# Utility
# ---------------------------
STOPWORDS = {"the","and","for","that","with","this","what","when","where","which","would","could","should",
             "your","from","have","just","like","also","been","they","them","will","how","can","you","are","its"}

def simple_main_motive(text, max_words=4):
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    words = [w for w in cleaned.split() if w not in STOPWORDS and len(w) > 2]
    if not words:
        return text[:40]
    return " ".join(words[:max_words]).capitalize()

def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return "⚠️ [Offline mode] Nexa simulated reply (no API key)."
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": MODEL, "messages": messages},
            headers=headers,
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Nexa error: {e}"

# ---------------------------
# CSS (Modern ChatGPT look)
# ---------------------------
st.markdown("""
<style>
.stApp { background-color: #0d1117; color: #e6f6ff; }
.chat-window {
    padding: 10px;
    border-radius: 10px;
    max-height: 75vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
}
.msg-user {
    background: #1f6feb;
    color: white;
    padding: 10px 15px;
    border-radius: 12px;
    width: fit-content;
    margin: 6px 0 6px auto;
}
.msg-ai {
    background: #21262d;
    color: #e6f6ff;
    padding: 10px 15px;
    border-radius: 12px;
    width: fit-content;
    margin: 6px auto 6px 0;
}
.input-row { display:flex; gap:8px; align-items:center; }
.small-muted { color:#9fb8c9; font-size:12px; margin-top:8px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session State Init
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
# keep typed text safe between runs
if "typed" not in st.session_state:
    st.session_state.typed = ""
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# ---------------------------
# Sidebar
# ---------------------------
with st.sidebar:
    st.markdown("## 💠 Nexa")
    new_name = st.text_input("Display name", st.session_state.user)
    if new_name:
        st.session_state.user = new_name

    st.markdown("---")
    st.markdown("### 💬 Conversations")
    convs = list_conversations(st.session_state.user)
    if convs:
        for conv in convs:
            if st.button(conv["title"] or "New chat", key=f"c{conv['id']}"):
                st.session_state.conv_id = conv["id"]
                st.experimental_rerun()

    if st.button("➕ New chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.experimental_rerun()

    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.experimental_rerun()

# ---------------------------
# Chat Window (top-aligned)
# ---------------------------
st.markdown("### 💭 Chat")
st.markdown('<div class="chat-window">', unsafe_allow_html=True)
messages = load_messages(st.session_state.conv_id)

for m in messages:
    if m["role"] == "assistant":
        st.markdown(f"<div class='msg-ai'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='msg-user'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# Microphone widget (embedded via components)
# ---------------------------
mic_html = r"""
<div id="mic-widget" style="font-family: Inter, sans-serif; color: white;">
  <div style="display:flex; gap:8px; align-items:center;">
    <button id="startMic" style="padding:6px 10px; border-radius:6px; background:#0f1720; color:#9fb8c9; border:1px solid #243240; cursor:pointer;">
      🎤 Start Mic
    </button>
    <button id="stopMic" style="padding:6px 10px; border-radius:6px; background:#0f1720; color:#9fb8c9; border:1px solid #243240; cursor:pointer;">■ Stop</button>
    <button id="copyText" style="padding:6px 10px; border-radius:6px; background:#0f1720; color:#9fb8c9; border:1px solid #243240; cursor:pointer;">📋 Copy</button>
    <div id="mic-status" style="margin-left:10px;color:#9fb8c9;">(mic idle)</div>
  </div>
  <div style="margin-top:8px;">
    <textarea id="transcript" rows="3" style="width:100%; border-radius:6px; background:#0b1116; color:#e6f6ff; border:1px solid #243240; padding:8px;" placeholder="Transcribed text will appear here..."></textarea>
  </div>
</div>

<script>
const startBtn = document.getElementById('startMic');
const stopBtn = document.getElementById('stopMic');
const copyBtn = document.getElementById('copyText');
const status = document.getElementById('mic-status');
const transcript = document.getElementById('transcript');

let recognition = null;
if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
  status.innerText = '(speech recognition not supported in this browser)';
  startBtn.disabled = true;
  stopBtn.disabled = true;
} else {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = true;
  recognition.continuous = true;

  recognition.onstart = () => { status.innerText = '(listening...)'; };
  recognition.onend = () => { status.innerText = '(stopped)'; };
  recognition.onerror = (e) => { status.innerText = '(error) ' + e.error; };

  recognition.onresult = (event) => {
    let text = '';
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      text += event.results[i][0].transcript;
    }
    transcript.value = text;
  };
}

startBtn.onclick = () => {
  if (recognition) recognition.start();
};
stopBtn.onclick = () => {
  if (recognition) recognition.stop();
};
copyBtn.onclick = async () => {
  try {
    await navigator.clipboard.writeText(transcript.value);
    status.innerText = '(copied to clipboard — paste into input)';
  } catch (e) {
    status.innerText = '(copy failed)';
  }
};
</script>
"""

# Render the mic widget below the chat and above input
components.html(mic_html, height=160)

st.markdown('<div class="small-muted">Use the mic to transcribe, press <strong>Copy</strong>, then paste into the message box and press Enter / Send.</div>', unsafe_allow_html=True)

# ---------------------------
# Input Row (text input + send + speak toggle)
# ---------------------------
col1, col2, col3 = st.columns([8, 1, 1])
with col1:
    # text_input is created here; don't mutate st.session_state['chat_box'] directly after creation
    chat_box_val = st.text_input("",
                                value=st.session_state.typed,
                                placeholder="Ask me anything and press Enter ↵",
                                key="chat_box")
with col2:
    send = st.button("Send")
with col3:
    # toggle for browser speech output; store in session state
    speak_toggle = st.checkbox("🎙️ Speak", value=st.session_state.speak_on_reply, key="speak_toggle")
    st.session_state.speak_on_reply = speak_toggle

# Determine if user submitted: send button or Enter changed text (safe check)
user_submitted = False
# If Send clicked -> submit
if send:
    user_submitted = True
# If Enter pressed: the text_input will have changed compared to st.session_state.typed
elif chat_box_val != st.session_state.typed:
    # treat change as submit only if non-empty and different from previous typed
    if chat_box_val.strip():
        user_submitted = True

# If submitted, handle message
if user_submitted and chat_box_val and chat_box_val.strip():
    user_text = chat_box_val.strip()

    # Save user message
    save_message(st.session_state.conv_id, st.session_state.user, "user", user_text)
    rename_conversation_if_default(st.session_state.conv_id, simple_main_motive(user_text))

    # Build context and call LLM
    history = load_messages(st.session_state.conv_id)
    payload = [{"role": "system", "content": "You are Nexa, a realistic AI assistant like ChatGPT."}]
    for m in history:
        # 'role' in DB rows is either 'assistant' or user; map to system roles for model
        payload.append({"role": m["role"], "content": m["content"]})

    with st.spinner("Nexa is thinking..."):
        reply = call_openrouter(payload)
        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    # Clear the text box safely: update our typed backup and the streamlit widget value
    st.session_state.typed = ""         # local backup
    # To clear the displayed text_input we set the same key to empty using session_state update
    st.session_state.chat_box = ""

    # After storing reply, optionally speak it using browser TTS (inject small HTML/JS)
    if st.session_state.speak_on_reply:
        safe_reply = html.escape(reply).replace("\n", " ")
        tts_html = f"""
        <script>
        try {{
          const utter = new SpeechSynthesisUtterance("{safe_reply}");
          // optional properties:
          utter.rate = 1.0;
          utter.pitch = 1.0;
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(utter);
        }} catch (e) {{
          console.error("TTS failed", e);
        }}
        </script>
        """
        components.html(tts_html, height=0)

    # rerun to show new chat message at the top area
    st.experimental_rerun()

# Keep the typed content in session state for next run (so we can detect Enter)
st.session_state.typed = chat_box_val or ""

# End of file

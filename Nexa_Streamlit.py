# Nexa_Streamlit_final2.py
# Stable Nexa UI: sidebar, centered chat, mic + send + speak, Enter to submit, input clears.

import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------
# Safe UTF-8 IO
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
# Database Setup (kept minimal & safe)
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
    conn = get_conn(); c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (user, title, created_at) VALUES (?, ?, ?)", (user, title, now))
    conn.commit(); cid = c.lastrowid; conn.close(); return cid

def list_conversations(user):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, title FROM conversations WHERE user=? ORDER BY id DESC", (user,))
    rows = c.fetchall(); conn.close(); return rows

def load_messages(cid):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    rows = c.fetchall(); conn.close(); return rows

def save_message(cid, sender, role, content):
    conn = get_conn(); c = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
              (cid, sender, role, content, ts))
    conn.commit(); conn.close()

def rename_conversation_if_default(cid, new_title):
    if not new_title: return
    try:
        conn = get_conn(); c = conn.cursor()
        c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
        row = c.fetchone()
        if row and (row["title"] == "New chat" or not row["title"]):
            c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid)); conn.commit()
    finally:
        try: conn.close()
        except: pass

# ---------------------------
# LLM call (OpenRouter)
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
# Styling + layout container
# ---------------------------
st.markdown("""
<style>
.stApp { background:#0d1117; color:#e6f6ff; }
.container-centered { max-width:900px; margin-left:auto; margin-right:auto; }
.chat-window {
    padding:14px; border-radius:10px;
    max-height:72vh; overflow-y:auto;
    display:flex; flex-direction:column; gap:6px;
    background: rgba(255,255,255,0.02);
    margin-bottom:8px;
}
.msg-user { background:#1f6feb; color:white; padding:10px 14px; border-radius:12px; margin-left:auto; max-width:85%; word-wrap:break-word; }
.msg-ai { background:#21262d; color:#e6f6ff; padding:10px 14px; border-radius:12px; margin-right:auto; max-width:85%; word-wrap:break-word; }
.input-row { display:flex; gap:8px; align-items:center; }
.small-muted { color:#9fb8c9; font-size:12px; margin-top:6px; }
.sidebar .stButton>button { width:100%; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session init
# ---------------------------
if "user" not in st.session_state: st.session_state.user = "You"
if "conv_id" not in st.session_state: st.session_state.conv_id = create_conversation(st.session_state.user)
# typed backup: used as source of truth for the input's initial value
if "typed" not in st.session_state: st.session_state.typed = ""
if "speak_on_reply" not in st.session_state: st.session_state.speak_on_reply = False

# ---------------------------
# Sidebar (left) — visible
# ---------------------------
with st.sidebar:
    st.markdown("## 💠 Nexa")
    st.session_state.user = st.text_input("Display name", st.session_state.user)
    st.markdown("---")
    st.markdown("### 💬 Conversations")
    convs = list_conversations(st.session_state.user)
    if convs:
        for conv in convs:
            if st.button(conv["title"] or "New chat", key=f"c{conv['id']}"):
                st.session_state.conv_id = conv["id"]
                # rerun by letting streamlit complete the click action (no experimental rerun)
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
# Page header + chat area (centered)
# ---------------------------
st.markdown('<div class="container-centered">', unsafe_allow_html=True)
st.markdown("### 💭 Nexa — Chat")

# chat window
chat_win = st.container()
with chat_win:
    st.markdown('<div class="chat-window" id="chat_window">', unsafe_allow_html=True)
    msgs = load_messages(st.session_state.conv_id)
    # show messages (oldest -> newest), top aligned (first message at top)
    for m in msgs:
        css = "msg-ai" if m["role"] == "assistant" else "msg-user"
        st.markdown(f"<div class='{css}'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="small-muted">Tip: allow microphone access. Press mic, it will record ~6s then auto-submit.</div>', unsafe_allow_html=True)

# ---------------------------
# Mic helper iframe & parent listener
# ---------------------------
# mic iframe HTML (creates its own SpeechRecognition, posts transcript to parent)
mic_iframe_html = r"""
<div id="mic_area">
  <button id="micBtn" style="padding:6px 10px;border-radius:6px;background:#0f1720;color:#9fb8c9;border:1px solid #243240;cursor:pointer;">
    🎤 Start Mic
  </button>
  <script>
  (function(){
    let rec = null;
    if (window.SpeechRecognition || window.webkitSpeechRecognition) {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      rec = new SR();
      rec.lang = 'en-US';
      rec.interimResults = false;
      rec.continuous = false;
      rec.onresult = function(e){
        let text = '';
        for (let i = e.resultIndex; i < e.results.length; ++i) text += e.results[i][0].transcript;
        window.parent.postMessage({type:'nexa_transcript', text: text}, '*');
      };
      rec.onend = function(){ document.getElementById('micBtn').innerText = '🎤 Start Mic'; };
      rec.onerror = function(){ document.getElementById('micBtn').innerText = '⚠ Mic'; };
    } else {
      document.getElementById('micBtn').disabled = true;
      document.getElementById('micBtn').innerText = 'No Mic';
    }

    document.getElementById('micBtn').onclick = function(){
      if (!rec) return;
      try { rec.start(); document.getElementById('micBtn').innerText = '🛑 Listening...'; } catch(e){}
      setTimeout(()=>{ try{ rec.stop(); } catch(e){} }, 6000);
    };
  })();
  </script>
</div>
"""

# Parent listener: when it receives the transcript, set the input value and click submit.
parent_listener = """
<script>
window.addEventListener('message', (e) => {
  try {
    if (e.data && e.data.type === 'nexa_transcript') {
      const txt = e.data.text || '';
      const input = document.querySelector('input[data-testid="stTextInput-input"]');
      if (input) {
        input.value = txt;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        // click the submit button of the form
        const btn = document.querySelector('form button[type="submit"]');
        if (btn) btn.click();
      }
    }
  } catch (err) { console.error(err); }
});
</script>
"""
st.markdown(parent_listener, unsafe_allow_html=True)

# ---------------------------
# Chat form (centered) — Text input + mic + speak + submit
# Use st.form_submit_button so Enter works and a submit button exists.
# ---------------------------
with st.form(key="chat_form", clear_on_submit=False):
    cols = st.columns([7, 1, 1, 1])
    # Important: value for text_input comes from st.session_state.typed so we can clear input after submit
    chat_text = cols[0].text_input("", value=st.session_state.typed, placeholder="Ask me anything and press Enter ↵", key="chat_input")
    # mic renders the iframe HTML (the iframe script posts to parent)
    cols[1].markdown(mic_iframe_html, unsafe_allow_html=True)
    # speak toggle (checkbox)
    speak_cb = cols[2].checkbox("🎙️ Speak", value=st.session_state.speak_on_reply, key="speak_toggle")
    # submit button (form submit)
    submitted = cols[3].form_submit_button("Send")

# make sure speak_on_reply mirrors the checkbox state
st.session_state.speak_on_reply = speak_cb

# ---------------------------
# Handle submit (the form submit triggers a rerun)
# - read the value from st.session_state['chat_input']
# - do NOT mutate st.session_state['chat_input'] after creation
# - to clear the field we update st.session_state.typed (which becomes the initial value next render)
# ---------------------------
if submitted:
    text = (st.session_state.get("chat_input", "") or "").strip()
    if text:
        # save user message
        save_message(st.session_state.conv_id, st.session_state.user, "user", text)
        # rename if default: small motive extractor (kept simple/minimal)
        try:
            motive = " ".join([w for w in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower()).split() if len(w) > 2][:4]).capitalize()
            rename_conversation_if_default(st.session_state.conv_id, motive)
        except Exception:
            pass

        # build payload from history
        history = load_messages(st.session_state.conv_id)
        payload = [{"role": "system", "content": "You are Nexa, a realistic AI assistant."}]
        for m in history:
            payload.append({"role": m["role"], "content": m["content"]})

        # call LLM (may block — spinner shown)
        with st.spinner("Nexa is thinking..."):
            reply = call_openrouter(payload)

        # save assistant reply
        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

        # optional browser TTS (no server libs)
        if st.session_state.speak_on_reply:
            safe = html.escape(reply).replace("\n", " ")
            components.html(f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));}}catch(e){{console.error(e);}}</script>", height=0)

        # clear typed backup (so next render the input initial value is empty)
        st.session_state.typed = ""
        # Note: do NOT set st.session_state['chat_input'] directly (avoids mutate-after-create error).
        # The form has already submitted and Streamlit re-runs — the text_input will be recreated with value from st.session_state.typed (empty).
        # final: rerun happens automatically after form submission.
else:
    # preserve typed value between runs so user doesn't lose partial typing
    st.session_state.typed = chat_text or st.session_state.get("typed", "")

st.markdown("</div>", unsafe_allow_html=True)

# Nexa_Streamlit.py — Stable final with mic near Send, Enter-send, input preserved
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
# DB helpers
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

def create_conversation(user, title="New chat"):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO conversations (user, title) VALUES (?, ?)", (user, title))
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

# ---------------------------
# Utilities
# ---------------------------
STOPWORDS = {"the","and","for","that","with","this","what","when","where","which","would","could","should",
             "your","from","have","just","like","also","been","they","them","will","how","can","you","are","its"}
def simple_main_motive(text, max_words=4):
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    words = [w for w in cleaned.split() if w not in STOPWORDS and len(w) > 2]
    return " ".join(words[:max_words]).capitalize() if words else text[:40]

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

# ---------------------------
# Styling & layout helpers
# ---------------------------
st.markdown("""
<style>
.stApp { background-color:#0d1117; color:#e6f6ff; }
.center-col { display:flex; justify-content:center; }
.chat-card { width:100%; max-width:900px; }
.chat-window { padding:12px; border-radius:10px; max-height:60vh; overflow-y:auto; background: rgba(255,255,255,0.02); }
.msg-user { background:#1f6feb; color:white; padding:10px 14px; border-radius:12px; width:fit-content; margin:6px 0 6px auto; }
.msg-ai { background:#21262d; color:#e6f6ff; padding:10px 14px; border-radius:12px; width:fit-content; margin:6px auto 6px 0; }
.controls { display:flex; gap:8px; align-items:center; }
.small-muted { color:#9fb8c9; font-size:12px; margin-top:6px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session state defaults
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "typed" not in st.session_state:
    st.session_state.typed = ""   # preserved input text (we will keep it after send)
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# ---------------------------
# Sidebar
# ---------------------------
with st.sidebar:
    st.markdown("## 💠 Nexa")
    st.session_state.user = st.text_input("Display name", st.session_state.user)
    st.markdown("---")
    st.markdown("### Conversations")
    convs = list_conversations(st.session_state.user)
    if convs:
        for conv in convs:
            if st.button(conv["title"] or "New chat", key=f"c{conv['id']}"):
                st.session_state.conv_id = conv["id"]; st.experimental_rerun()
    if st.button("➕ New chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user); st.experimental_rerun()
    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db(); st.experimental_rerun()
    st.markdown("---")
    st.session_state.speak_on_reply = st.checkbox("🔊 Speak replies (browser TTS)", value=st.session_state.speak_on_reply)

# ---------------------------
# Centered chat card
# ---------------------------
col_left, col_mid, col_right = st.columns([1, 2, 1])
with col_mid:
    st.markdown('<div class="chat-card">', unsafe_allow_html=True)
    st.markdown("### 💭 Chat")
    st.markdown('<div class="chat-window" id="chat-window">', unsafe_allow_html=True)
    # messages top-aligned
    msgs = load_messages(st.session_state.conv_id)
    for m in msgs:
        css = "msg-ai" if m["role"] == "assistant" else "msg-user"
        st.markdown(f"<div class='{css}'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-muted">Tip: type and press Enter or click Send. Use mic to transcribe then press Send.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Mic component HTML (fills the input field)
# - placed next to Send (so it appears near send)
# ---------------------------
mic_html = r"""
<script>
(function(){
  // minimal mic UI that posts transcript into the page's input element
  const container = document.createElement('div');
  container.style.display='inline-block';
  container.style.width='100%';
  // create a button; Streamlit will render this inside an empty markdown element
  container.innerHTML = '<button id="nexa_mic_btn" style="padding:6px 10px;border-radius:6px;background:#0f1720;color:#9fb8c9;border:1px solid #243240;cursor:pointer">🎤</button>';
  document.getElementById('nexa_mic_container')?.appendChild(container);

  // speech recognition
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    const btn = document.getElementById('nexa_mic_btn');
    if (btn) { btn.disabled = true; btn.title = 'SpeechRecognition not supported'; }
    return;
  }
  const rec = new SpeechRecognition();
  rec.lang = 'en-US';
  rec.continuous = false;
  rec.interimResults = false;

  const btn = document.getElementById('nexa_mic_btn');
  btn.addEventListener('click', () => {
    if (btn.dataset.listening === '1') {
      rec.stop();
      return;
    }
    btn.dataset.listening = '1';
    btn.textContent = '🛑';
    try { rec.start(); } catch(e) { /* ignore */ }
    // safety stop after 7s
    setTimeout(()=>{ try{ rec.stop(); }catch(e){} }, 7000);
  });

  rec.onresult = (evt) => {
    const transcript = evt.results[0][0].transcript || '';
    // find the text input - Streamlit sets data-testid attribute on input elements
    const input = document.querySelector('input[data-testid="stTextInput-input"]');
    if (input) {
      input.value = transcript;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      // focus it
      input.focus();
    }
  };
  rec.onend = () => {
    btn.dataset.listening = '0';
    btn.textContent = '🎤';
  };
})();
</script>
"""

# ---------------------------
# Input form (uses a form so Enter submits reliably on mobile & desktop)
# - place mic placeholder and Send on the right
# ---------------------------
with col_mid:
    with st.form(key="send_form", clear_on_submit=False):
        cols = st.columns([8, 1, 1])
        # note: we do not mutate st.session_state['chat_box'] after creation
        chat_val = cols[0].text_input("", value=st.session_state.typed, placeholder="Ask me anything and press Enter ↵", key="chat_box")
        # mic injected into the middle column (appears left of send visually)
        cols[1].markdown('<div id="nexa_mic_container"></div>', unsafe_allow_html=True)
        cols[1].components = components  # no-op but keeps context
        # send button (form submit)
        submitted = cols[2].form_submit_button("Send")

    # render mic script once (small height)
    components.html(mic_html, height=1)

# ---------------------------
# Submission handling
# ---------------------------
# If user submitted via form, handle it here.
# We intentionally do not assign to st.session_state['chat_box'] after widget instantiation.
if submitted and chat_val and chat_val.strip():
    user_text = chat_val.strip()
    # store user message
    save_message(st.session_state.conv_id, st.session_state.user, "user", user_text)
    rename = simple_main_motive(user_text)
    # attempt to rename conversation title if needed
    try:
        # best-effort: update title if New chat (no harm if not present)
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT title FROM conversations WHERE id=?", (st.session_state.conv_id,))
        row = cur.fetchone()
        if row and (not row["title"] or row["title"] == "New chat"):
            cur.execute("UPDATE conversations SET title=? WHERE id=?", (rename, st.session_state.conv_id))
            conn.commit()
        conn.close()
    except Exception:
        pass

    # build context
    history = load_messages(st.session_state.conv_id)
    payload = [{"role": "system", "content": "You are Nexa, a realistic AI assistant."}]
    for m in history:
        payload.append({"role": m["role"], "content": m["content"]})

    # call LLM (spinner)
    with st.spinner("Nexa is thinking..."):
        reply = call_openrouter(payload)
        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    # browser TTS if enabled
    if st.session_state.speak_on_reply:
        safe = html.escape(reply).replace("\n", " ")
        tts = f"<script>try{{ speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}')); }}catch(e){{console.error(e);}}</script>"
        components.html(tts, height=0)

    # preserve input (user requested "text should not disappear"); keep typed same as chat_val
    st.session_state.typed = chat_val
    # refresh to show new messages
    st.experimental_rerun()
else:
    # keep typed up-to-date for next run
    st.session_state.typed = chat_val or st.session_state.typed

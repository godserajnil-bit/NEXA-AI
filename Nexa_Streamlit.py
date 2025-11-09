# Nexa_Streamlit.py — Stable: form submit, mic -> auto-submit, Enter clears input, browser TTS
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------
# Safe UTF-8
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
# DB helpers (unchanged logic)
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

def rename_conversation_if_default(cid, new_title):
    if not new_title: return
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
    row = c.fetchone()
    if row and (row["title"] == "New chat" or not row["title"]):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid)); conn.commit()
    conn.close()

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
# Styling (chat top-aligned, longer box)
# ---------------------------
st.markdown("""
<style>
.stApp { background-color:#0d1117; color:#e6f6ff; }
.container-centered { max-width:900px; margin-left:auto; margin-right:auto; }
.chat-window {
    padding:14px; border-radius:10px;
    max-height:78vh; overflow-y:auto;
    display:flex; flex-direction:column; justify-content:flex-start;
    background: rgba(255,255,255,0.02);
}
.msg-user { background:#1f6feb; color:white; padding:10px 14px; border-radius:12px; width:fit-content; margin:8px 0 8px auto; max-width:80%; word-wrap:break-word; }
.msg-ai { background:#21262d; color:#e6f6ff; padding:10px 14px; border-radius:12px; width:fit-content; margin:8px auto 8px 0; max-width:80%; word-wrap:break-word; }
.input-row { display:flex; gap:8px; align-items:center; margin-top:10px; }
.input-row .stTextInput>div>div>input { height:42px; font-size:15px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session state init
# ---------------------------
if "user" not in st.session_state: st.session_state.user = "You"
if "conv_id" not in st.session_state: st.session_state.conv_id = create_conversation(st.session_state.user)
if "typed" not in st.session_state: st.session_state.typed = ""
if "speak_on_reply" not in st.session_state: st.session_state.speak_on_reply = False

# ---------------------------
# Page layout header
# ---------------------------
st.markdown('<div class="container-centered">', unsafe_allow_html=True)
st.markdown("### 💭 Nexa — Chat")

# ---------------------------
# Chat display
# ---------------------------
st.markdown('<div class="chat-window">', unsafe_allow_html=True)
for m in load_messages(st.session_state.conv_id):
    css = "msg-ai" if m["role"] == "assistant" else "msg-user"
    st.markdown(f"<div class='{css}'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("")  # spacer

# ---------------------------
# Inject parent listener for mic iframe messages
# (This listens for postMessage from the iframe and sets the text input value,
#  then triggers the form submit button click programmatically.)
# ---------------------------
st.markdown("""
<script>
window.addEventListener('message', (e) => {
  try {
    if (e.data && e.data.type === 'transcript') {
      const txt = e.data.text || '';
      // find the first text input (chat form)
      const input = document.querySelector('input[data-testid="stTextInput-input"]');
      if (input) {
        input.value = txt;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        // find form submit button inside a form and click it (submit)
        const btn = document.querySelector('form button[type="submit"]');
        if (btn) btn.click();
      }
    }
  } catch(err) { console.error(err); }
});
</script>
""", unsafe_allow_html=True)

# ---------------------------
# Mic iframe (posts transcript to parent)
# ---------------------------
mic_iframe = r"""
<div>
  <button id="micBtn" style="padding:6px 10px;border-radius:6px;background:#0f1720;color:#9fb8c9;border:1px solid #243240;cursor:pointer;">🎤 Start Mic</button>
  <script>
  let rec=null;
  if (window.SpeechRecognition || window.webkitSpeechRecognition) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    rec = new SR();
    rec.lang = 'en-US';
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (e) => {
      let text = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        text += e.results[i][0].transcript;
      }
      // send transcript to parent window (Streamlit page)
      window.parent.postMessage({type:'transcript', text: text}, '*');
    };
    rec.onend = () => { document.getElementById('micBtn').innerText = '🎤 Start Mic'; };
    rec.onerror = (ev) => { document.getElementById('micBtn').innerText = '⚠ mic error'; };
  } else {
    document.getElementById('micBtn').disabled = true;
    document.getElementById('micBtn').innerText = 'No Mic Support';
  }

  document.getElementById('micBtn').onclick = () => {
    if (!rec) return;
    // start, then auto-stop after 6s (shorter mobile-friendly listening)
    document.getElementById('micBtn').innerText = '🛑 Listening...';
    try { rec.start(); } catch(e) { console.warn(e); }
    setTimeout(()=>{ try { rec.stop(); } catch(e){} }, 6000);
  };
  </script>
</div>
"""

# Place mic and input inside a form so Enter triggers submit (use st.form)
with st.form(key="chat_form", clear_on_submit=False):
    cols = st.columns([8, 1, 1])
    # text input (value is taken from session typed)
    chat_text = cols[0].text_input("", value=st.session_state.typed, placeholder="Ask me anything and press Enter ↵", key="chat_box")
    # mic rendered as markdown (button + JS will post message to parent)
    cols[1].markdown(mic_iframe, unsafe_allow_html=True)
    # speak toggle to the right of mic (near send)
    cols[2].checkbox("🎙️ Speak", value=st.session_state.speak_on_reply, key="speak_toggle")
    submit = st.form_submit_button("Send")

# Update session state for speak toggle
st.session_state.speak_on_reply = st.session_state.get("speak_toggle", st.session_state.speak_on_reply)

# ---------------------------
# Handle submission: Enter or Send
# ---------------------------
if submit:
    text = (chat_text or "").strip()
    if text:
        # save user message, auto-rename if first meaningful text
        save_message(st.session_state.conv_id, st.session_state.user, "user", text)
        rename_conversation_if_default(st.session_state.conv_id, (lambda t: " ".join([w for w in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in t.lower()).split() if len(w)>2][:4]).capitalize())(text))
        # build history for model
        history = load_messages(st.session_state.conv_id)
        payload = [{"role":"system","content":"You are Nexa, a realistic AI assistant."}]
        for m in history:
            payload.append({"role": m["role"], "content": m["content"]})
        # call model
        with st.spinner("Nexa is thinking..."):
            reply = call_openrouter(payload)
        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

        # optional browser TTS (speak_on_reply)
        if st.session_state.speak_on_reply:
            safe = html.escape(reply).replace("\n"," ")
            components.html(f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));}}catch(e){{console.error(e);}}</script>", height=0)

        # clear typed session value so input is empty on next render
        st.session_state.typed = ""
        # Important: do not assign st.session_state['chat_box'] after widget creation.
        # Instead set typed backup and allow the form to render its default from typed next run.
        # Trigger a rerun by calling st.experimental_rerun if available, otherwise rely on Streamlit's rerun after form submit.
        try:
            st.experimental_rerun()
        except Exception:
            # some Streamlit builds may not have experimental_rerun; that's okay,
            # form submit already causes a rerun in most environments.
            pass
else:
    # keep typed value persistent across runs (so change detection works)
    st.session_state.typed = chat_text or st.session_state.get("typed", "")

st.markdown('</div>', unsafe_allow_html=True)

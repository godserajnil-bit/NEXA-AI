# Nexa_Streamlit_final_ui.py
# Streamlit chat: sidebar conversations, centered welcome, mic + send, browser TTS.
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------
# Safe IO
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
# DB helpers (sqlite)
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def reset_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_conn(); c = conn.cursor()
    c.execute("""
      CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT, title TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    """)
    c.execute("""
      CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER, sender TEXT, role TEXT, content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    """)
    conn.commit(); conn.close()

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
# OpenRouter call (LLM)
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
# Styling
# ---------------------------
st.markdown("""
<style>
/* page background */
.stApp { background: #0f1720; color: #e6f6ff; }

/* container center */
.container-centered { max-width: 1100px; margin-left:auto; margin-right:auto; padding-top:12px; }

/* sidebar narrower */
.css-1d391kg { min-width: 260px; } /* rough adjustment; may vary with Streamlit version */

/* header / welcome area */
.welcome {
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  min-height: 280px; border-radius:12px; margin-bottom:14px;
  background: linear-gradient(180deg, rgba(255,255,255,0.01), rgba(255,255,255,0.0));
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
}
.examples { display:flex; gap:14px; justify-content:center; margin-top:12px; flex-wrap:wrap; }
.example-card { background: rgba(255,255,255,0.02); padding:12px 18px; border-radius:8px; color:#dbeafe; }

/* chat window */
.chat-window {
    padding:14px; border-radius:12px;
    max-height:58vh; overflow-y:auto;
    display:flex; flex-direction:column; gap:8px;
    background: transparent;
}
.msg-user {
    background: #06b6d4; color: #042027; padding:10px 14px; border-radius:12px;
    margin-left:auto; max-width:78%; word-wrap:break-word;
}
.msg-ai {
    background: #111827; color:#e6f6ff; padding:10px 14px; border-radius:12px;
    margin-right:auto; max-width:78%; word-wrap:break-word;
}

/* input row */
.input-row { display:flex; gap:8px; align-items:center; justify-content:center; margin-top:8px; }
.input-box { flex:1; border-radius:12px; background:#0b1220; padding:6px 10px; }
input[data-testid="stTextInput-input"] { background:transparent !important; color:#e6f6ff !important; }

/* small UX */
.small-muted { color:#9fb8c9; font-size:12px; margin-top:8px; text-align:center; }

/* logo animation */
.logo-circle {
  width:74px; height:74px; border-radius:14px; background:linear-gradient(135deg,#06b6d4,#7c3aed);
  display:flex; align-items:center; justify-content:center; font-weight:800; font-family:Inter, sans-serif;
  color:white; transform: scale(0.4); animation: zoomIn 700ms forwards;
}
@keyframes zoomIn { to { transform: scale(1); } }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session init
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
# Sidebar content
# ---------------------------
with st.sidebar:
    st.markdown("## 🔷 Nexa")
    st.session_state.user = st.text_input("Display name", st.session_state.user)
    st.markdown("---")
    st.markdown("### Conversations")
    convs = list_conversations(st.session_state.user)
    if convs:
        for conv in convs:
            btn_label = conv["title"] or "New chat"
            if st.button(btn_label, key=f"conv_{conv['id']}"):
                st.session_state.conv_id = conv["id"]
                st.experimental_rerun()
    if st.button("➕ New chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.experimental_rerun()
    st.markdown("---")
    # voice enable toggle in left panel
    st.session_state.speak_on_reply = st.checkbox("Enable Nexa voice (TTS)", value=st.session_state.speak_on_reply)
    st.markdown("---")
    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.experimental_rerun()

# ---------------------------
# Page header + welcome + chat area
# ---------------------------
st.markdown('<div class="container-centered">', unsafe_allow_html=True)

# header row with animated NX logo and title
header_col1, header_col2 = st.columns([1, 5])
with header_col1:
    st.markdown('<div class="logo-circle">NX</div>', unsafe_allow_html=True)
with header_col2:
    st.markdown("<h1 style='margin:6px 0 0 0'>Nexa</h1>", unsafe_allow_html=True)
    st.markdown("<div class='small-muted'>Your AI assistant — ask anything</div>", unsafe_allow_html=True)

st.markdown("<div class='welcome'>", unsafe_allow_html=True)
st.markdown("<h2 style='margin:6px 0 0 0'>Welcome to Nexa</h2>", unsafe_allow_html=True)
st.markdown("<div class='examples'>", unsafe_allow_html=True)
st.markdown("<div class='example-card'>Explain quantum computing in simple terms</div>", unsafe_allow_html=True)
st.markdown("<div class='example-card'>Give me creative ideas for a birthday</div>", unsafe_allow_html=True)
st.markdown("<div class='example-card'>How to make an HTTP request in JavaScript?</div>", unsafe_allow_html=True)
st.markdown("</div></div>", unsafe_allow_html=True)

# Chat window (centered)
st.markdown('<div class="chat-window" id="chat_window">', unsafe_allow_html=True)
messages = load_messages(st.session_state.conv_id)
if messages:
    for m in messages:
        if m["role"] == "assistant":
            st.markdown(f"<div class='msg-ai'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='msg-user'>{html.escape(m['content'])}</div>", unsafe_allow_html=True)
else:
    st.markdown("<div class='msg-ai'>Hello — ask me anything. I can help with code, ideas, explanations and more.</div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="small-muted">Chat history is shown on the left. Use the mic to speak (desktop Chrome recommended).</div>', unsafe_allow_html=True)

# ---------------------------
# Mic JS (posts transcript to parent)
# ---------------------------
mic_js = r"""
<script>
(function(){
  // send function for transcript
  function postTranscript(t){
    window.parent.postMessage({type:'nexa_transcript', text: t}, '*');
  }
  // attach listener for messages from iframe (none here) - not needed
  // This script only defines a global function to be called from the mic button below.
  window.nexa_postTranscript = postTranscript;
})();
</script>
"""
st.markdown(mic_js, unsafe_allow_html=True)

# Mic button and listener HTML (this starts Web SpeechRecognition, records ~6s, posts transcript to parent)
mic_widget = r"""
<div id="mic_wrapper" style="display:flex; align-items:center; justify-content:center;">
  <button id="nexaMic" style="padding:8px 12px;border-radius:8px;background:#062c34;color:#d1fae5;border:1px solid rgba(255,255,255,0.04);cursor:pointer">🎤</button>
</div>
<script>
const micBtn = document.getElementById('nexaMic');
let rec=null;
if (window.SpeechRecognition || window.webkitSpeechRecognition) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  rec = new SR();
  rec.lang='en-US'; rec.interimResults=false; rec.continuous=false;
  rec.onresult = (e) => {
    let text='';
    for (let i=e.resultIndex;i<e.results.length;++i) text+=e.results[i][0].transcript;
    window.parent.postMessage({type:'nexa_transcript', text:text}, '*');
  };
  rec.onend = ()=>{ micBtn.innerText='🎤'; micBtn.disabled=false; };
  rec.onerror = ()=>{ micBtn.innerText='⚠'; micBtn.disabled=false; };
} else {
  micBtn.disabled=true; micBtn.innerText='No Mic';
}
micBtn.onclick = ()=> {
  if (!rec) return;
  try { rec.start(); micBtn.innerText='🛑'; micBtn.disabled=true; setTimeout(()=>{ try{ rec.stop(); }catch(e){} }, 6000); } catch(e){}
};
</script>
"""
# we won't render mic_widget here; we'll include it in the form area (so its button is next to the send button)

# ---------------------------
# Chat form (so Enter works reliably)
# - Use st.form with form_submit_button to ensure "submit" exists (avoids missing submit-button warnings)
# - Provide initial value from st.session_state.typed
# ---------------------------
with st.form(key="chat_form"):
    cols = st.columns([7, 1, 1])
    # input box (value driven by session_state typed)
    chat_text = cols[0].text_input("", value=st.session_state.typed, placeholder="Send a message...", key="chat_input")
    # mic button (render JS widget here so it appears left of Send)
    cols[1].markdown(mic_widget, unsafe_allow_html=True)
    # speak toggle small (we already mirrored to sidebar, but keep small checkbox for quick toggle)
    cols[2].markdown("<div style='display:flex;flex-direction:column;gap:6px;align-items:center;'><label style='font-size:12px;color:#9fb8c9'>Speak</label></div>", unsafe_allow_html=True)
    submitted = st.form_submit_button("Send")

# JS: parent listens for transcript messages and injects them into the form input and auto-submits the form
# This script must run on the page; it fills the text input and clicks the Send button in the form.
inject_listener = r"""
<script>
window.addEventListener('message', (e)=>{
  try {
    if(!e.data) return;
    if (e.data.type === 'nexa_transcript') {
      const text = e.data.text || '';
      // find the most recent text input (our chat_input)
      const inputs = document.querySelectorAll('input[data-testid="stTextInput-input"]');
      if (inputs && inputs.length) {
        const inp = inputs[inputs.length-1];
        inp.value = text;
        inp.dispatchEvent(new Event('input', {bubbles:true}));
        // find the last form submit button and click it
        const forms = document.querySelectorAll('form');
        if (forms.length){
          const lastForm = forms[forms.length-1];
          const btn = lastForm.querySelector('button[type="submit"]');
          if (btn) btn.click();
        }
      }
    }
  } catch(err) { console.error(err); }
});
</script>
"""
st.markdown(inject_listener, unsafe_allow_html=True)

# ---------------------------
# Handle submission
# ---------------------------
if submitted:
    text = (st.session_state.get("chat_input","") or "").strip()
    if text:
        # save user message
        save_message(st.session_state.conv_id, st.session_state.user, "user", text)
        # rename conv if default (quick motive)
        try:
            motive = " ".join([w for w in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower()).split() if len(w)>2][:4]).capitalize()
            rename_conversation_if_default(st.session_state.conv_id, motive)
        except Exception:
            pass

        # build payload and call LLM
        history = load_messages(st.session_state.conv_id)
        payload = [{"role":"system","content":"You are Nexa, a helpful assistant."}]
        for m in history:
            # message DB has 'role' values we stored; pass them as-is
            payload.append({"role": m["role"], "content": m["content"]})
        with st.spinner("Nexa is thinking..."):
            reply = call_openrouter(payload)
        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

        # optional browser TTS: use sidebar toggle
        if st.session_state.speak_on_reply:
            safe = html.escape(reply).replace("\n"," ")
            components.html(f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));}}catch(e){{console.error(e);}}</script>", height=0)

        # clear typed stored value so next render the input is empty
        st.session_state.typed = ""
        # Note: we DO NOT mutate st.session_state['chat_input'] after creation; form will re-render using typed as new initial.
        # After processing, re-run will happen naturally (form submission causes rerun).
else:
    # preserve typed between runs
    st.session_state.typed = chat_text or st.session_state.get("typed", "")

st.markdown("</div>", unsafe_allow_html=True)

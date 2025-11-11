import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

---------------------------
Safe IO
---------------------------
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("LANG", "en_US.UTF-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

---------------------------
Config
---------------------------
st.set_page_config(page_title="Nexa", layout="wide")
DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

---------------------------
DB helpers (sqlite)
---------------------------
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
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, created_at) VALUES (?, ?, ?, ?, ?)", (cid, sender, role, content, ts))
    conn.commit()
    conn.close()

def rename_conversation_if_default(cid, new_title):
    if not new_title:
        return
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT title FROM conversations WHERE id=?", (cid,))
        row = c.fetchone()
        if row and (row["title"] == "New chat" or not row["title"]):
            c.execute("UPDATE conversations SET title=? WHERE id=?", (new_title, cid))
            conn.commit()
    finally:
        try:
            conn.close()
        except:
            pass

---------------------------
OpenRouter call (LLM)
---------------------------
def call_openrouter(messages):
    if not OPENROUTER_API_KEY:
        return "⚠️ [Offline mode] Nexa simulated reply (no API key)."
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", json={"model": MODEL, "messages": messages}, headers=headers, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ Nexa error: {e}"

---------------------------
Styling (Updated for Clean UI/UX)
---------------------------
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap');
        body { font-family: 'Inter', sans-serif; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); color: #333; }
        .header { text-align: center; padding: 20px; background: rgba(255,255,255,0.9); border-radius: 15px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .logo { font-size: 3em; font-weight: 600; color: #4CAF50; animation: fadeIn 2s; }
        .title { font-size: 2.5em; font-weight: 600; color: #333; }
        .subtitle { font-size: 1.2em; color: #666; }
        .welcome { text-align: center; margin: 20px 0; }
        .example { background: #fff; padding: 10px; border-radius: 10px; margin: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); cursor: pointer; }
        .chat-container { max-width: 800px; margin: 0 auto; padding: 20px; }
        .user-msg { background: #007bff; color: white; padding: 15px; border-radius: 15px; margin: 10px 0; text-align: right; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .assistant-msg { background: #f1f1f1; color: #333; padding: 15px; border-radius: 15px; margin: 10px 0; text-align: left; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .timestamp { font-size: 0.8em; color: #999; margin-top: 5px; }
        .sidebar { background: #fff; padding: 15px; border-radius: 10px; }
        .form-row { display: flex; align-items: center; gap: 10px; }
        .mic-btn { background: #28a745; color: white; border: none; padding: 10px; border-radius: 50%; cursor: pointer; }
        .send-btn { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; }
        .footer { text-align: center; font-size: 0.9em; color: #666; margin-top: 20px; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @media (max-width: 768px) { .chat-container { padding: 10px; } .header { padding: 10px; } }
    </style>
""", unsafe_allow_html=True)

---------------------------
Session init
---------------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "typed" not in st.session_state:
    st.session_state.typed = ""
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False
if "logo_shown" not in st.session_state:
    st.session_state.logo_shown = False

---------------------------
Logo Popup on App Open (New Feature)
---------------------------
if not st.session_state.logo_shown:
    with st.modal("Welcome to Nexa!", clear_on_close=True):
        st.markdown('<div style="text-align: center; animation: fadeIn 2s;"><h1 class="logo">NX</h1><p>Your AI assistant is ready!</p></div>', unsafe_allow_html=True)
        if st.button("Get Started"):
            st.session_state.logo_shown = True
            st.rerun()
else:
    # Sidebar content (unchanged except minor styling)
    with st.sidebar:
        st.markdown('<div class="sidebar">', unsafe_allow_html=True)
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
        st.session_state.speak_on_reply = st.checkbox("Enable Nexa voice (TTS)", value=st.session_state.speak_on_reply)
        st.markdown("---")
        if st.button("🧹 Reset Database"):
            reset_db()
            st.session_state.conv_id = create_conversation(st.session_state.user)
            st.experimental_rerun()
        st.markdown('</div>', unsafe_allow_html=True)

---------------------------
Page header + welcome + chat area (Updated for Clean UI)
---------------------------
st.markdown('<div class="header">', unsafe_allow_html=True)
header_col1, header_col2 = st.columns([1, 5])
with header_col1:
    st.markdown('<div class="logo">NX</div>', unsafe_allow_html=True)
with header_col2:
    st.markdown('<div class="title">Nexa</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Your AI assistant — ask anything</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="welcome">', unsafe_allow_html=True)
st.markdown("### Welcome to Nexa")
st.markdown('<div class="example" onclick="document.getElementById(\'chat_input\').value=\'Explain quantum computing in simple terms\'; document.querySelector(\'button[type=submit]\').click();">💡 Explain quantum computing in simple terms</div>', unsafe_allow_html=True)
st.markdown('<div class="example" onclick="document.getElementById(\'chat_input\').value=\'Give me creative ideas for a birthday\'; document.querySelector(\'button[type=submit]\').click();">🎉 Give me creative ideas for a birthday</div>', unsafe_allow_html=True)
st.markdown('<div class="example" onclick="document.getElementById(\'chat_input\').value=\'How to make an HTTP request in JavaScript?\'; document.querySelector(\'button[type=submit]\').click();">💻 How to make an HTTP request in JavaScript?</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Chat window (centered, updated styling)
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
messages = load_messages(st.session_state.conv_id)
if messages:
    for m in messages:
        ts = m["created_at"].split("T")[1][:5] if "T" in m["created_at"] else ""
        if m["role"] == "assistant":
            st.markdown(f'<div class="assistant-msg">{html.escape(m["content"])}<div class="timestamp">{ts}</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="user-msg">{html.escape(m["content"])}<div class="timestamp">{ts}</div></div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="assistant-msg">Hello — ask me anything. I can help with code, ideas, explanations and more.</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<p style="text-align: center; color: #666;">Chat history is shown on the left. Use the mic to speak (desktop Chrome recommended).</p>', unsafe_allow_html=True)

---------------------------
Mic JS (unchanged)
---------------------------
mic_js = r"""
<script>
if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
    console.warn("Speech recognition not supported");
} else {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    recognition.maxAlternatives = 1;
    window.startMic = function() {
        recognition.start();
    };
    recognition.onresult = function(event) {
        const transcript = event.results[0][0].transcript;
        window.parent.postMessage({type: 'transcript', text: transcript}, '*');
    };
    recognition.onerror = function(event) {
        console.error('Speech recognition error:', event.error);
    };
}
</script>
"""
st.markdown(mic_js, unsafe_allow_html=True)

# Mic button and listener HTML (this starts Web SpeechRecognition, records ~6s, posts transcript to parent)
mic_widget = r"""
<button class="mic-btn" onclick="window.startMic()">🎤</button>
"""
# we won't render mic_widget here; we'll include it in the form area (so its button is next to the send button)

---------------------------
Chat form (so Enter works reliably)
- Use st.form with form_submit_button to ensure "submit" exists (avoids missing submit-button warnings)
- Provide initial value from st.session_state.typed
---------------------------
with st.form(key="chat_form"):
    cols = st.columns([7, 1, 1])  # input box (value driven by session_state typed)
    chat_text = cols[0].text_input("", value=st.session_state.typed, placeholder="Send a message...", key="chat_input")
    # mic button (render JS widget here so it appears left of Send)
    cols[1].markdown(mic_widget, unsafe_allow_html=True)
    # speak toggle small (we already mirrored to sidebar, but keep small checkbox for quick toggle)
    cols[2].markdown("""
    <input type="checkbox" id="speak_toggle" onchange="window.speakOnReply = this.checked;">
    <label for="speak_toggle">Speak</label>
    """, unsafe_allow_html=True)
    submitted = st.form_submit_button("Send")

# JS: parent listens for transcript messages and injects them into the form input and auto-submits the form
# This script must run on the page; it fills the text input and clicks the Send button in the form.
inject_listener = r"""
<script>
window.addEventListener('message', function(event) {
    if (event.data.type === 'transcript') {
        const input = document.getElementById('chat_input');
        if (input) {
            input.value = event.data.text;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            const form = input.closest('form');
            if (form) {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) submitBtn.click();
            }
        }
    }
});
</script>
"""
st.markdown(inject_listener, unsafe_allow_html=True)

---------------------------
Handle submission
---------------------------
if submitted:
    text = (st.session_state.get("chat_input", "") or "").strip()
    if text:
        # save user message
        save_message(st.session_state.conv_id, st.session_state.user, "user", text)
        # rename conv if default (quick motive)
        try:
            motive = " ".join([w for w in "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower()).split() if len(w) > 2][:4]).capitalize()
            rename_conversation_if_default(st.session_state.conv_id, motive)
        except Exception:
            pass

        # build payload and call LLM
        history = load_messages(st.session_state.conv_id)
        payload = [{"role": "system", "content": "You are Nexa, a helpful assistant."}]
        for m in history:
            # message DB has 'role' values we stored; pass them as-is
            payload.append({"role": m["role"], "content": m["content"]})
        with st.spinner("Nexa is thinking..."):
            reply = call_openrouter(payload)
        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

        # optional browser TTS: use sidebar toggle
        if st.session_state.speak_on_reply:
            safe = html.escape(reply).replace("\n", " ")
            components.html(f"<script>try{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));}}catch(e){{console.error(e);}}</script>", height=0)

        # clear typed stored value so next render the input is empty
        st.session_state.typed = ""
        # Note: we DO NOT mutate st.session_state['chat_input'] after creation; form will re-render using typed as new initial.
        # After processing, re-run will happen naturally (form submission causes rerun).
        st.rerun()  # Added to force immediate UI update
else:  # preserve typed between runs
    st.session_state.typed = chat_text or st.session_state.get("typed", "")

st.markdown("""
<div class="footer">
    Powered by Nexa | Built with Streamlit
</div>
""", unsafe_allow_html=True)

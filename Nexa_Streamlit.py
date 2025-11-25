 # Nexa_Streamlit.py
# Combined final: Nexa UI with logo+quote top-center (disappear on typing), DB, mic, LLM wrapper, sidebar black, light-grey chat
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components
import base64
from PIL import Image

# --------------------
# UTF-8 I/O safe
# --------------------
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# --------------------
# Config
# --------------------
st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")
DB_PATH = "nexa.db"
MODEL = os.getenv("NEXA_MODEL", "gpt-3.5-turbo")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# --------------------
# Helpers: DB
# --------------------
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
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        sender TEXT,
        role TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

if not os.path.exists(DB_PATH):
    reset_db()

def create_conversation(username, title="New chat"):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (user, title, created_at) VALUES (?, ?, ?)", (username, title, now))
    conn.commit()
    cid = c.lastrowid
    conn.close()
    return cid

def list_conversations(username):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, title FROM conversations WHERE user=? ORDER BY id DESC", (username,))
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

# --------------------
# LLM wrapper (OpenRouter) — unchanged
# --------------------
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

# --------------------
# Quote fetch (fetch once per new session/load)
# --------------------
def get_random_quote():
    try:
        r = requests.get("https://api.quotable.io/random", timeout=5)
        if r.status_code == 200:
            j = r.json()
            return f"{j.get('content','')} — {j.get('author','')}"
    except Exception:
        pass
    return "Believe in yourself and all that you are."


# ✅ ADD THIS DIRECTLY BELOW ⬇️
def get_real_time_answer(query):
    try:
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_redirect=1&no_html=1"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("AbstractText"):
                return data["AbstractText"]
            if data.get("Answer"):
                return data["Answer"]
    except:
        pass
    return None

# --------------------
# Session init for UI flags & user
# --------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "show_intro" not in st.session_state:
    # show_intro = True means logo+quote visible until typing or new chat toggles it
    st.session_state.show_intro = True
if "intro_quote" not in st.session_state:
    # fetch once when session starts — this gives a new quote on fresh session (app open)
    st.session_state.intro_quote = get_random_quote()

# --------------------
# Styling: black sidebar and light-grey main — minimal and safe CSS
# --------------------
st.markdown("""
<style>

/* Sidebar background */
[data-testid="stSidebar"] > div:first-child {
  background-color: #000000;
  color: #ffffff;
}

/* Main background */
.main {
  background: #e6e6e6 !important;
}

/* ===== CHAT BUBBLES ===== */
.chat-user, .chat-ai {
    background: #000000;
    color: #ffffff;
    padding: 12px 14px;
    border-radius: 14px;
    margin: 10px 0;
    max-width: 80%;
    line-height: 1.4;
    font-size: 15px;
}

.chat-user { margin-left: auto; }
.chat-ai { margin-right: auto; }

/* ===== INTRO ===== */
#nexa-intro { 
  text-align: center; 
  margin-top: 6px; 
  margin-bottom: 14px; 
}
#nexa-logo { 
  width: 72px; 
  height: auto; 
  display: block; 
  margin: 0 auto 8px auto; 
}
#nexa-quote { 
  color: #333; 
  font-style: italic; 
}

/* ===== TEXT INPUT ===== */
.stTextInput > div > div > input {
  background: #000 !important;
  color: #fff !important;
  border-radius: 100px !important;
  padding: 12px 18px !important;
  border: 1px solid #222 !important;
}

/* ===== PLUS BUTTON POSITION ===== */
form[data-testid="stForm"] {
  position: fixed;
  bottom: 25px;
  left: 50%;
  transform: translateX(-50%);
  padding: 0 !important;
  margin: 0 !important;
  background: transparent !important;
  border: none !important;
  z-index: 9999;
}

/* Keep chat above bar */
.block-container {
  padding-bottom: 160px !important;
}

/* Style uploader as circle */
section[data-testid="stFileUploaderDropzone"] {
  width: 56px !important;
  height: 56px !important;
  border-radius: 50% !important;
  border: 2px solid black !important;
  background: black !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  cursor: pointer !important;
  padding: 0 !important;
}

/* Remove Streamlit text inside */
section[data-testid="stFileUploaderDropzone"] span {
  display: none !important;
}

/* Add + sign */
section[data-testid="stFileUploaderDropzone"]::after {
  content: "+";
  color: white;
  font-size: 32px;
  font-weight: 600;
}

/* Hover effect */
section[data-testid="stFileUploaderDropzone"]:hover {
  box-shadow: 0 0 0 6px rgba(0,0,0,0.12);
  transform: scale(1.05);
}

/* Hide submit button (but keep working) */
form[data-testid="stForm"] button {
  display: none !important;
}

</style>
""", unsafe_allow_html=True)

# --------------------
# Sidebar content (black) — keep functionality same
# --------------------
with st.sidebar:
    st.markdown("## Nexa", unsafe_allow_html=True)
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
                # when opening existing conv, we still want intro hidden
                st.session_state.show_intro = False
                st.rerun()
    else:
        st.info("No conversations yet — press New Chat to start.")

    if st.button("➕ New Chat"):
        # create a new conversation and show intro (logo+quote)
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.session_state.show_intro = True
        st.session_state.intro_quote = get_random_quote()  # new quote for new session-like behavior
        st.rerun()

    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.session_state.show_intro = True
        st.session_state.intro_quote = get_random_quote()
        st.rerun()

    st.markdown("---")
    st.checkbox("🔊 Nexa speak replies (browser TTS)", key="speak_on_reply")
    st.markdown("---")
    st.markdown("Quick actions")
    if st.button("Open YouTube"):
        components.html("<script>window.open('https://www.youtube.com','_blank');</script>", height=0)
    if st.button("Open Google"):
        components.html("<script>window.open('https://www.google.com','_blank');</script>", height=0)

# --------------------
# Main area: top-center logo+quote (hide when typing), messages list, input form
# --------------------
st.markdown("<div style='max-width:980px;margin-left:auto;margin-right:auto;'>", unsafe_allow_html=True)

# Intro (logo + quote) — shown only when show_intro is True
if st.session_state.get("show_intro", True):
    # use the uploaded image path as logo (developer-provided path)
    logo_path = "/mnt/data/Screenshot (8).png"  # local image available in environment
    # If the file doesn't exist, we simply don't break — show text fallback
    if os.path.exists(logo_path):
        st.markdown(f"""
        <div id="nexa-intro">
          <img id="nexa-logo" src="file://{logo_path}" alt="Nexa Logo"/>
          <div id="nexa-quote">{html.escape(st.session_state.intro_quote)}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div id="nexa-intro">
          <div style="font-weight:700;font-size:22px;">NEXA</div>
          <div id="nexa-quote">{html.escape(st.session_state.intro_quote)}</div>
        </div>
        """, unsafe_allow_html=True)
else:
    # keep a small spacer so layout doesn't jump too hard
    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

# Messages display area
messages = load_messages(st.session_state.conv_id)
if not messages:
    st.markdown("<div style='color:#444;padding:12px;border-radius:8px;'>Start the conversation — type below or use mic 🎤</div>", unsafe_allow_html=True)
else:
    for m in messages:
        content = html.escape(m["content"] or "")
        if m["role"] == "assistant":
            st.markdown(f"<div class='chat-ai'>{content}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-user'>{content}</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)  # end main container wrapper

# --------------------
# PLUS icon only (Image Upload Form)
# --------------------
with st.form("nexa_input_form", clear_on_submit=True):
    uploaded_image = st.file_uploader(
        "",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=False,
        key="nexa_image",
        label_visibility="collapsed"
    )
    submitted = st.form_submit_button("")

# --------------------
# Handle submit server-side (store message, call LLM)
# --------------------
if submitted and uploaded_image is not None:

    text = "[Image sent]"

    # ---------- IMAGE HANDLING ----------
    image_bytes = uploaded_image.getvalue()
    st.session_state.last_image = image_bytes

    # Show image in chat
    with st.chat_message("user"):
        st.image(image_bytes, caption="You sent", use_column_width=True)

    # ---------- SAVE USER MESSAGE ----------
    save_message(
        st.session_state.conv_id,
        st.session_state.user,
        "user",
        text
    )

    # Hide intro
    st.session_state.show_intro = False

    # ---------- BUILD HISTORY ----------
    history = [
        {"role": "system", "content": "You are Nexa, a helpful assistant that can see and understand images."}
    ]

    for m in load_messages(st.session_state.conv_id):
        history.append({
            "role": m["role"],
            "content": m["content"]
        })

    # ---------- ADD IMAGE ----------
    import base64
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")

    history.append({
        "role": "user",
        "content": [
            {"type": "text", "text": "Analyze this image"},
            {
                "type": "image_url",
                "image_url": f"data:image/png;base64,{img_b64}"
            }
        ]
    })

    # ---------- CALL AI ----------
    with st.spinner("Nexa is analyzing..."):
        try:
            reply = call_openrouter(history)
        except Exception as e:
            reply = f"⚠️ Error: {e}"

    # ---------- DISPLAY AI MESSAGE ----------
    with st.chat_message("assistant"):
        st.markdown(reply)

    # ---------- SAVE AI REPLY ----------
    save_message(
        st.session_state.conv_id,
        "Nexa",
        "assistant",
        reply
    )

    # ---------- OPTIONAL TTS ----------
    if st.session_state.get("speak_on_reply", False):
        safe = html.escape(reply).replace("\n", " ")
        components.html(f"""
        <script>
        speechSynthesis.cancel();
        speechSynthesis.speak(new SpeechSynthesisUtterance("{safe}"));
        </script>
        """, height=0)

    st.rerun()

# End — keep code intact, DB persists history across refreshes

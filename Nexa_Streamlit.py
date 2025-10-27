# Nexa_Streamlit.py
# Streamlit-native conversion of Nexa (chat + client-side voice input/output + SQLite)
# Usage:
#  - create requirements.txt (see instructions)
#  - Deploy to Streamlit Cloud or run locally: `streamlit run Nexa_Streamlit.py`

import streamlit as st
import sqlite3
import os
import re
from datetime import datetime, timedelta
import hashlib

def generate_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password_hash(stored_hash, password):
    return stored_hash == hashlib.sha256(password.encode()).hexdigest()
import requests
import json

st.set_page_config(page_title="Nexa", layout="wide", initial_sidebar_state="expanded")

# ---------------------------
# Configuration
# ---------------------------
DB_FILE = "nexa_streamlit.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

OPENROUTER_API_KEY = "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"  # Optional: set your openrouter/openai key here
MODEL = "gpt-4o-mini"

# ---------------------------
# DB utilities
# ---------------------------
def get_db_conn():
    conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_conn(); c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user TEXT NOT NULL,
      title TEXT,
      created TEXT NOT NULL
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      conversation_id INTEGER,
      sender TEXT,
      role TEXT,
      content TEXT,
      image TEXT,
      timestamp TEXT
    )""")
    conn.commit(); conn.close()

init_db()

# ---------------------------
# Simple title extractor
# ---------------------------
STOPWORDS = {
    "the","and","for","that","with","this","what","when","where","which","would",
    "could","should","there","their","about","your","from","have","just","like",
    "also","been","they","them","will","how","can","a","an","in","on","of","to","is","are","it"
}

def simple_main_motive(text: str, max_words: int = 5) -> str:
    if not text:
        return "New chat"
    cleaned = re.sub(r"[^0-9A-Za-z\s]", " ", text.lower())
    words = [w for w in re.split(r"\s+", cleaned) if w and len(w) > 2 and w not in STOPWORDS]
    if not words:
        short = text.strip()
        return (short[:40] + "...") if len(short) > 40 else short
    seen = set(); chosen = []
    for w in words:
        if w in seen: continue
        seen.add(w); chosen.append(w)
        if len(chosen) >= max_words: break
    title = " ".join(chosen)
    return title.capitalize() if title else "New chat"

# ---------------------------
# Auth helpers (simple)
# ---------------------------
def create_user(username: str, password: str):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
              (username, generate_password_hash(password)))
    conn.commit(); conn.close()

def verify_user(username: str, password: str) -> bool:
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    row = c.fetchone(); conn.close()
    if not row: return False
    return check_password_hash(row["password"], password)

# ---------------------------
# Conversation helpers
# ---------------------------
def create_conversation(user: str) -> int:
    conn = get_db_conn(); c = conn.cursor()
    created = datetime.utcnow().isoformat()
    c.execute("INSERT INTO conversations (user, title, created) VALUES (?, ?, ?)", (user, None, created))
    conn.commit(); cid = c.lastrowid; conn.close()
    return cid

def list_conversations(user: str):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT id, title, created FROM conversations WHERE user=? ORDER BY id DESC", (user,))
    rows = c.fetchall(); conn.close()
    return [dict(id=r["id"], title=(r["title"] if r["title"] else "New chat"), created=r["created"]) for r in rows]

def rename_conversation_once(conv_id: int, title: str):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (conv_id,))
    row = c.fetchone()
    if row and not row["title"]:
        c.execute("UPDATE conversations SET title=? WHERE id=?", (title, conv_id))
        conn.commit()
    conn.close()

def delete_conversation(conv_id: int):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    c.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit(); conn.close()

def save_message(conv_id: int, sender: str, role: str, content: str, image: str = None):
    ts = datetime.utcnow().isoformat()
    conn = get_db_conn(); c = conn.cursor()
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, image, timestamp) VALUES (?,?,?,?,?,?)",
              (conv_id, sender, role, content, image, ts))
    conn.commit(); conn.close()

def load_messages(conv_id: int):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT sender, role, content, image, timestamp FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
    rows = c.fetchall(); conn.close()
    return [dict(sender=r["sender"], role=r["role"], content=r["content"], image=r["image"], timestamp=r["timestamp"]) for r in rows]

# ---------------------------
# News helper (optional)
# ---------------------------
def get_news(query: str, max_results: int = 4):
    # Keep minimal: uses gnews if key present in OPENROUTER_API_KEY variable (not used by default)
    return f"(News disabled) You searched: {query}"

# ---------------------------
# LLM call (optional) using openrouter endpoint
# ---------------------------
def call_llm(messages):
    if not OPENROUTER_API_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL, "messages": messages}
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=18)
        r.raise_for_status()
        raw = r.json()
        return raw["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(LLM error) {e}"

# ---------------------------
# Session state init
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "current_conv" not in st.session_state:
    st.session_state.current_conv = None
if "persona" not in st.session_state:
    st.session_state.persona = "Friendly"
if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = True
if "mic_text" not in st.session_state:
    st.session_state.mic_text = ""

# ---------------------------
# Simple login/register UI
# ---------------------------
def login_panel():
    st.sidebar.title("Nexa — Login")
    choice = st.sidebar.radio("Action", ("Login", "Register"))
    username = st.sidebar.text_input("Username", key="login_user")
    password = st.sidebar.text_input("Password", type="password", key="login_pass")
    if choice == "Register":
        if st.sidebar.button("Create account"):
            if not username or not password:
                st.sidebar.error("Enter username and password")
            else:
                try:
                    create_user(username, password)
                    st.sidebar.success("Registered — you can now login")
                except Exception as e:
                    st.sidebar.error(f"Error: {e}")
    else:
        if st.sidebar.button("Login"):
            if verify_user(username, password):
                st.session_state.user = username
                st.experimental_rerun()
            else:
                st.sidebar.error("Invalid credentials")

def logout():
    st.session_state.user = None
    st.session_state.current_conv = None
    st.experimental_rerun()

if not st.session_state.user:
    login_panel()
    st.info("Please login or register in the left panel to use Nexa.")
    st.stop()

# ---------------------------
# App layout
# ---------------------------
# Sidebar - conversations & controls
with st.sidebar:
    st.markdown("## Nexa — Assistant")
    st.write(f"Logged in as: **{st.session_state.user}**")
    if st.button("New chat"):
        st.session_state.current_conv = create_conversation(st.session_state.user)
    if st.button("Logout"):
        logout()
    st.markdown("---")
    st.selectbox("Persona", options=["Friendly","Neutral","Cheerful","Professional"], index=["Friendly","Neutral","Cheerful","Professional"].index(st.session_state.persona), key="persona_select", on_change=lambda: st.session_state.__setitem__("persona", st.session_state.persona_select))
    st.checkbox("Voice output", value=st.session_state.voice_enabled, key="voice_chk", on_change=lambda: st.session_state.__setitem__("voice_enabled", st.session_state.voice_chk))
    st.markdown("---")
    # show conversations
    convs = list_conversations(st.session_state.user)
    if convs:
        st.markdown("### Conversations")
        for c in convs:
            title = c["title"] or "New chat"
            if st.button(f"{title}  (#{c['id']})", key=f"open_{c['id']}"):
                st.session_state.current_conv = c["id"]

# Main area
col1, col2 = st.columns([3, 7])  # left: messages (smaller), right: message area (bigger)
with col2:
    st.markdown("<h2 style='margin:0'>Nexa</h2>", unsafe_allow_html=True)
    if st.session_state.current_conv:
        # get title
        conn = get_db_conn(); c = conn.cursor(); c.execute("SELECT title FROM conversations WHERE id=?", (st.session_state.current_conv,)); row = c.fetchone(); conn.close()
        conv_title = row["title"] if row and row["title"] else "New chat"
        st.markdown(f"**Conversation:** {conv_title}")
    else:
        st.markdown("**No conversation selected — create a New chat or open one from the sidebar**")

    # Chat messages area
    messages_container = st.container()
    def render_messages():
        messages_container.empty()
        with messages_container:
            if st.session_state.current_conv:
                msgs = load_messages(st.session_state.current_conv)
                for m in msgs:
                    if m["role"] == "assistant":
                        st.markdown(f"<div style='padding:10px;border-radius:8px;background:rgba(255,255,255,0.02);margin:6px 0'><b>Assistant</b><div style='margin-top:6px'>{st.session_state.get('last_assistant_override', m['content'])}</div></div>", unsafe_allow_html=True)
                    else:
                        # user messages
                        st.markdown(f"<div style='text-align:right;padding:6px;margin:6px 0'><b>You</b><div style='display:inline-block;background:linear-gradient(180deg, rgba(0,255,255,0.06), rgba(0,255,255,0.03));padding:8px;border-radius:8px'>{m['content']}</div></div>", unsafe_allow_html=True)
    render_messages()

    # input + send
    user_input = st.text_input("Ask Nexa...", value=st.session_state.mic_text or "", key="user_input")

    # Buttons for attach mic (embedded component) and send
    cols = st.columns([1,1,6])
    with cols[0]:
        # mic HTML component - returns recognized text (if any) to Python
        mic_html = r"""
        <!doctype html>
        <html>
        <body>
        <button id="mic">🎤 Start</button>
        <script>
        const button = document.getElementById('mic');
        let recognizing = false;
        let recognition = null;
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
          const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
          recognition = new SR();
          recognition.lang = 'en-US';
          recognition.interimResults = false;
          recognition.continuous = false;
          recognition.onresult = function(e){
            const text = e.results[0][0].transcript;
            // send to streamlit (special wrapper recognized by st.components)
            const payload = {'text': text};
            // streamlit recognizes window.parent.postMessage({isStreamlitMessage:true, type:'FROM_COMPONENT', text: text}, '*')
            window.parent.postMessage({isStreamlitMessage:true, type:'FROM_COMPONENT', text: text}, '*');
          };
          recognition.onend = function(){ recognizing=false; button.innerText='🎤 Start'; }
        } else {
          button.disabled = true; button.innerText = 'Not supported';
        }
        button.onclick = function(){
          if(!recognition) return;
          if(recognizing){ recognition.stop(); recognizing=false; button.innerText='🎤 Start'; }
          else{ recognition.start(); recognizing=true; button.innerText='⏸ Stop'; }
        };
        </script>
        </body>
        </html>
        """
        # The component returns a dict when it posts a message with isStreamlitMessage:true
        import streamlit.components.v1 as components
        mic_ret = components.html(mic_html, height=60)
        # When mic_ret is not None, it will be the returned dict from JS (text)
        if mic_ret:
            # mic_ret may be a dict or a string; handle both
            if isinstance(mic_ret, dict) and "text" in mic_ret:
                st.session_state.mic_text = mic_ret["text"]
                # set the text_input to the captured text by re-running
                st.experimental_rerun()
            elif isinstance(mic_ret, str) and mic_ret.strip():
                st.session_state.mic_text = mic_ret
                st.experimental_rerun()

    with cols[1]:
        if st.button("Send"):
            text = user_input.strip()
            if not text:
                st.warning("Type something or use the mic.")
            else:
                # ensure conversation exists
                if not st.session_state.current_conv:
                    st.session_state.current_conv = create_conversation(st.session_state.user)
                conv_id = st.session_state.current_conv
                save_message(conv_id, st.session_state.user, "user", text, None)
                # auto title
                rename_conversation_once(conv_id, simple_main_motive(text, max_words=5))
                # Generate reply (LLM if key present else persona-driven)
                reply = ""
                if text.lower().startswith("news:"):
                    reply = get_news(text[5:].strip())
                else:
                    # If LLM available, build history and call
                    if OPENROUTER_API_KEY:
                        history = load_messages(conv_id)
                        messages = [{"role":"system","content":f"You are Nexa, a helpful assistant. Persona: {st.session_state.persona}."}]
                        for m in history:
                            role = "assistant" if m["role"] == "assistant" else "user"
                            messages.append({"role": role, "content": m["content"]})
                        messages.append({"role":"user","content": text})
                        llm_resp = call_llm(messages)
                        reply = llm_resp if llm_resp is not None else "(LLM returned nothing)"
                    else:
                        p = st.session_state.persona
                        if p == "Friendly":
                            reply = f"🙂 Sure — {text}. I'd be happy to help!"
                        elif p == "Neutral":
                            reply = f"{text}"
                        elif p == "Cheerful":
                            reply = f"🎉 Yay! Here's a quick take: {text} — hope that helps!"
                        elif p == "Professional":
                            reply = f"As requested, here's a concise response: {text}."
                        else:
                            reply = f"[{p}] I heard: {text or '(image)'}"
                save_message(conv_id, "assistant", "assistant", reply, None)
                st.session_state.mic_text = ""  # clear mic buffer
                st.session_state.last_reply_for_tts = reply
                st.experimental_rerun()

    with cols[2]:
        st.write("")  # spacer
        # TTS: when last reply exists and voice_enabled is True, render a small component that triggers speechSynthesis
        last = st.session_state.get("last_reply_for_tts", "")
        if last and st.session_state.voice_enabled:
            tts_html = f"""
            <!doctype html>
            <html>
            <body>
            <script>
            const txt = {json.dumps(last)};
            // speak immediately
            if ('speechSynthesis' in window) {{
                const u = new SpeechSynthesisUtterance(txt);
                u.rate = 1; u.pitch = 1;
                // cancel previous
                window.speechSynthesis.cancel();
                window.speechSynthesis.speak(u);
            }}
            // no message back to streamlit
            </script>
            <div></div>
            </body>
            </html>
            """
            # we render but keep it short height
            components.html(tts_html, height=10)

with col1:
    # Secondary column: show conversation list and history controls
    st.write("## History")
    convs = list_conversations(st.session_state.user)
    for c in convs:
        cols = st.columns([3,1,1])
        cols[0].markdown(f"**{c['title']}**")
        if cols[1].button("Open", key=f"o{c['id']}"):
            st.session_state.current_conv = c['id']; st.experimental_rerun()
        if cols[2].button("Delete", key=f"d{c['id']}"):
            delete_conversation(c['id']); st.session_state.current_conv = None; st.experimental_rerun()

# Footer / small help
st.markdown("---")
st.markdown("Microphone & TTS are browser-based (Web Speech API). Works best in Chrome or Edge. If mic button shows 'Not supported', your browser doesn't expose the API.")


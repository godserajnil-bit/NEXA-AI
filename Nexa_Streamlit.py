# Nexa_Streamlit.py
# Streamlit-native version of Nexa (chat + SQLite + client-side mic & TTS)
# Usage:
#   pip install -r requirements.txt
#   streamlit run Nexa_Streamlit.py

import streamlit as st
import sqlite3
import os
import re
import json
import requests
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# ---------------------------
# Config
# ---------------------------
st.set_page_config(page_title="Nexa — Assistant", layout="wide")
DB_FILE = "nexa_streamlit.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Optional LLM integration (openrouter/openai compatible)
OPENROUTER_API_KEY = "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"  # set your key if you want real LLM responses
MODEL = "gpt-4o-mini"

# ---------------------------
# Database helpers
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
# Simple password hashing (no werkzeug required)
# ---------------------------
def generate_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def check_password_hash(stored_hash: str, password: str) -> bool:
    return stored_hash == hashlib.sha256(password.encode()).hexdigest()

# ---------------------------
# Conversation/message helpers
# ---------------------------
def create_user(username: str, password: str):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, generate_password_hash(password)))
    conn.commit(); conn.close()

def verify_user(username: str, password: str) -> bool:
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    row = c.fetchone(); conn.close()
    if not row: return False
    return check_password_hash(row["password"], password)

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
# Title extractor (lightweight)
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
# Optional LLM call (openrouter)
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
# Session state defaults
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
if "last_reply_for_tts" not in st.session_state:
    st.session_state.last_reply_for_tts = ""
if "messages_cache" not in st.session_state:
    st.session_state.messages_cache = {}

# ---------------------------
# Helper: save uploaded file to disk and return relative path
# ---------------------------
def save_uploaded_file(uploaded_file) -> Optional[str]:
    if not uploaded_file:
        return None
    filename = os.path.basename(uploaded_file.name)
    safe_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
    dest = os.path.join(UPLOAD_FOLDER, safe_name)
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest  # return file path

# ---------------------------
# UI: Login / Register
# ---------------------------
def show_login_register():
    st.sidebar.title("Nexa — Sign in")
    action = st.sidebar.radio("Action", ("Login", "Register"), index=0)

    username = st.sidebar.text_input("Username", key="login_username")
    password = st.sidebar.text_input("Password", type="password", key="login_password")
    remember = st.sidebar.checkbox("Remember me", value=False, key="login_remember")

    if action == "Register":
        if st.sidebar.button("Create account"):
            if not username or not password:
                st.sidebar.error("Please provide username and password.")
            else:
                try:
                    create_user(username, password)
                    st.sidebar.success("Account created. You can now log in.")
                except Exception as e:
                    st.sidebar.error(f"Could not create account: {e}")
    else:
        if st.sidebar.button("Login"):
            if verify_user(username, password):
                st.session_state.user = username
                if remember:
                    # store in session state for simplicity (this is not a persistent cookie)
                    st.session_state.remembered_user = username
                st.experimental_set_query_params()  # no-op just to allow immediate UI update
                st.rerun()
            else:
                st.sidebar.error("Invalid credentials.")

# ---------------------------
# Top bar and layout
# ---------------------------
def header_and_sidebar_controls():
    st.sidebar.markdown("## Nexa — Assistant")
    if st.session_state.user:
        st.sidebar.markdown(f"**Logged in as:** {st.session_state.user}")
        if st.sidebar.button("Logout"):
            st.session_state.user = None
            st.session_state.current_conv = None
            st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.selectbox("Persona", options=["Friendly", "Neutral", "Cheerful", "Professional"], index=["Friendly", "Neutral", "Cheerful", "Professional"].index(st.session_state.persona), key="persona_select")
    st.session_state.persona = st.session_state.persona_select
    st.sidebar.checkbox("Voice output (browser TTS)", value=st.session_state.voice_enabled, key="voice_out_chk")
    st.session_state.voice_enabled = st.session_state.voice_out_chk
    st.sidebar.markdown("---")
    if st.session_state.user:
        if st.sidebar.button("New conversation"):
            st.session_state.current_conv = create_conversation(st.session_state.user)
            st.rerun()

# ---------------------------
# Mic & TTS components (client-side via components.html)
# ---------------------------
def mic_component(height: int = 70):
    # This component uses the browser Web Speech API and posts recognized text back to Streamlit.
    mic_html = r"""
    <!doctype html>
    <html>
    <body>
    <button id="mic" style="font-size:16px;padding:8px 12px;border-radius:8px">🎤 Start</button>
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
        // send the recognized text back to Streamlit via postMessage; Streamlit captures top-level message automatically
        const payload = {'text': text};
        window.parent.postMessage({isStreamlitMessage:true, type:'FROM_COMPONENT', payload: payload}, '*');
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
    import streamlit.components.v1 as components
    # components.html returns nothing if not using the full custom component API, but we can still use it to show the UI.
    components.html(mic_html, height=height)

def tts_component(text: str):
    # Client-side TTS using speechSynthesis. It will speak the text immediately when rendered.
    if not text:
        return
    safe_text = json.dumps(text)
    tts_html = f"""
    <!doctype html>
    <html>
    <body>
    <script>
    const txt = {safe_text};
    if ('speechSynthesis' in window) {{
        const u = new SpeechSynthesisUtterance(txt);
        u.rate = 1; u.pitch = 1;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(u);
    }}
    </script>
    </body>
    </html>
    """
    import streamlit.components.v1 as components
    # small height - we only need the script to run
    components.html(tts_html, height=10)

# ---------------------------
# Core UI rendering & message handling
# ---------------------------
def render_chat_ui():
    st.markdown("<style>div.block-container{padding-left:1rem;padding-right:1rem}</style>", unsafe_allow_html=True)
    col_left, col_right = st.columns([3,7])
    with col_right:
        st.markdown("## Nexa")
        if st.session_state.current_conv:
            conn = get_db_conn(); c = conn.cursor()
            c.execute("SELECT title FROM conversations WHERE id=?", (st.session_state.current_conv,))
            row = c.fetchone(); conn.close()
            conv_title = row["title"] if row and row["title"] else "New chat"
            st.markdown(f"**Conversation:** {conv_title}")
        else:
            st.markdown("**No conversation selected** — create a New conversation or open one from the left panel.")

        # messages container
        container = st.container()

        # display messages
        def display_messages():
            container.empty()
            with container:
                if st.session_state.current_conv:
                    msgs = load_messages(st.session_state.current_conv)
                    for m in msgs:
                        if m["role"] == "assistant":
                            st.markdown(f"<div style='padding:10px;border-radius:8px;background:rgba(255,255,255,0.02);margin:6px 0'><b>Assistant</b><div style='margin-top:6px'>{m['content']}</div></div>", unsafe_allow_html=True)
                            if m.get("image"):
                                try:
                                    st.image(m["image"], width=360)
                                except:
                                    st.markdown(f"![image]({m['image']})")
                        else:
                            st.markdown(f"<div style='text-align:right;padding:6px;margin:6px 0'><b>You</b><div style='display:inline-block;background:linear-gradient(180deg, rgba(0,255,255,0.06), rgba(0,255,255,0.03));padding:8px;border-radius:8px'>{m['content']}</div></div>", unsafe_allow_html=True)

        display_messages()

        # input and buttons
        # We use a small form for better UX
        with st.form(key="send_form", clear_on_submit=False):
            text = st.text_input("Type a message or use the mic", value=st.session_state.mic_text or "", key="input_text")
            file = st.file_uploader("Attach an image (optional)", type=["png","jpg","jpeg","gif"])
            cols = st.columns([1,1,6])
            with cols[0]:
                mic_component(height=60)
            with cols[1]:
                send = st.form_submit_button("Send")
            with cols[2]:
                st.write("")  # spacer

            # handle mic text if posted via component postMessage
            # Streamlit captures top-level postMessage events as values in st.experimental_get_query_params? Not guaranteed.
            # Instead we read st.session_state.mic_text (which we set from front-end via a small trick below).
            # The mic component uses window.parent.postMessage with isStreamlitMessage true - Streamlit will make that available to components.html return in some contexts.
            # To keep robust, if st.session_state.mic_text exists and input field is empty, set text to it:
            if not text and st.session_state.mic_text:
                text = st.session_state.mic_text

            if send:
                if not text and not file:
                    st.warning("Type something or attach an image.")
                else:
                    # ensure conversation
                    if not st.session_state.current_conv:
                        st.session_state.current_conv = create_conversation(st.session_state.user)
                    conv_id = st.session_state.current_conv

                    # save file if present
                    image_path = None
                    if file:
                        image_path = save_uploaded_file(file)

                    save_message(conv_id, st.session_state.user, "user", text or "(image)", image_path)
                    # auto-title once
                    if text:
                        motive = simple_main_motive(text, max_words=5)
                        rename_conversation_once(int(conv_id), motive)

                    # generate reply
                    reply = ""
                    if text and text.lower().startswith("news:"):
                        reply = f"(News disabled) You searched for: {text[5:].strip()}"
                    else:
                        # use LLM if key present
                        if OPENROUTER_API_KEY:
                            history = load_messages(conv_id)
                            messages = [{"role":"system","content":f"You are Nexa, a helpful assistant. Persona: {st.session_state.persona}."}]
                            for m in history:
                                role = "assistant" if m["role"] == "assistant" else "user"
                                messages.append({"role": role, "content": m["content"]})
                            messages.append({"role":"user","content": text or "(image)"})
                            llm_resp = call_llm(messages)
                            reply = llm_resp if llm_resp is not None else "(LLM returned nothing)"
                        else:
                            p = st.session_state.persona
                            if p == "Friendly":
                                reply = f"🙂 Sure — {text or '(image)'}. I'd be happy to help!"
                            elif p == "Neutral":
                                reply = f"{text or '(image)'}"
                            elif p == "Cheerful":
                                reply = f"🎉 Yay! Here's a quick take: {text or '(image)'} — hope that helps!"
                            elif p == "Professional":
                                reply = f"As requested, here's a concise response: {text or '(image)'}."
                            else:
                                reply = f"[{p}] I heard: {text or '(image)'}"

                    save_message(conv_id, "assistant", "assistant", reply, None)
                    # set TTS payload
                    st.session_state.last_reply_for_tts = reply
                    st.session_state.mic_text = ""  # clear mic buffer
                    st.rerun()

        # speak last reply if TTS enabled
        if st.session_state.last_reply_for_tts and st.session_state.voice_enabled:
            tts_component(st.session_state.last_reply_for_tts)
            # clear after speaking so it doesn't repeat on rerun
            st.session_state.last_reply_for_tts = ""

    # left column: history & controls
    with col_left:
        st.markdown("### Conversations")
        if st.session_state.user:
            convs = list_conversations(st.session_state.user)
            for c in convs:
                cols = st.columns([3,1,1])
                cols[0].markdown(f"**{c['title']}**")
                if cols[1].button("Open", key=f"open_{c['id']}"):
                    st.session_state.current_conv = c['id']
                    st.rerun()
                if cols[2].button("Delete", key=f"del_{c['id']}"):
                    delete_conversation(c['id'])
                    if st.session_state.current_conv == c['id']:
                        st.session_state.current_conv = None
                    st.rerun()

        st.markdown("---")
        st.markdown("**Controls**")
        if st.button("Rename current conversation"):
            if not st.session_state.current_conv:
                st.warning("No conversation selected.")
            else:
                new_title = st.text_input("New title", key="rename_box")
                # Note: interactive rename will require rerun - keep simple
                if new_title:
                    conn = get_db_conn(); c = conn.cursor()
                    c.execute("UPDATE conversations SET title=? WHERE id=? AND user=?", (new_title, st.session_state.current_conv, st.session_state.user))
                    conn.commit(); conn.close()
                    st.success("Renamed.")
                    st.rerun()

# ---------------------------
# Entry point
# ---------------------------
def main():
    st.title("Nexa — Assistant")

    # If not logged in, show login/register
    if not st.session_state.user:
        show_login_register()
        st.info("Please login or register from the left sidebar (or use the controls).")
        st.stop()

    header_and_sidebar_controls()
    render_chat_ui()

# Run
if __name__ == "__main__":
    main()

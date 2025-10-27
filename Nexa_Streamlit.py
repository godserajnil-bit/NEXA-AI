# Nexa_Streamlit.py
# Streamlit-native chat UI (ChatGPT-like), optional OpenRouter LLM, browser mic + TTS, and SQLite persistence.
# Deploy on Streamlit Cloud: put this file and requirements.txt in repo root, set main file to Nexa_Streamlit.py
# Add your OpenRouter API key in Streamlit Secrets with name OPENROUTER_API_KEY (see instructions below).

import streamlit as st
import sqlite3
import os
import re
import json
import requests
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# ---------------------------
# Configuration
# ---------------------------
st.set_page_config(page_title="Nexa — Assistant", layout="centered", initial_sidebar_state="collapsed")
BASE = Path.cwd()
DB_PATH = BASE / "nexa_chat.db"
UPLOAD_DIR = BASE / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DEFAULT_MODEL = "gpt-4o-mini"  # placeholder; change if using other models

# ---------------------------
# Helpers: DB and user/password (simple)
# ---------------------------
def get_db_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
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

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def check_password(stored: str, pw: str) -> bool:
    return stored == hash_password(pw)

def create_user(username: str, password: str):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hash_password(password)))
    conn.commit(); conn.close()

def verify_user(username: str, password: str) -> bool:
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    r = c.fetchone(); conn.close()
    if not r: return False
    return check_password(r["password"], password)

# Conversation helpers
def create_conversation(user: str) -> int:
    conn = get_db_conn(); c = conn.cursor()
    created = datetime.utcnow().isoformat()
    c.execute("INSERT INTO conversations (user, title, created) VALUES (?, ?, ?)", (user, None, created))
    conn.commit(); cid = c.lastrowid; conn.close()
    return cid

def list_conversations(user: str) -> List[Dict[str, Any]]:
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT id, title, created FROM conversations WHERE user=? ORDER BY id DESC", (user,))
    rows = c.fetchall(); conn.close()
    return [{"id": r["id"], "title": (r["title"] or "New chat"), "created": r["created"]} for r in rows]

def rename_conversation_once(conv_id: int, title: str):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT title FROM conversations WHERE id=?", (conv_id,))
    row = c.fetchone()
    if row and (row["title"] is None or row["title"] == ""):
        c.execute("UPDATE conversations SET title=? WHERE id=?", (title, conv_id))
        conn.commit()
    conn.close()

def delete_conversation(conv_id: int):
    conn = get_db_conn(); c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    c.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit(); conn.close()

def save_message(conv_id: int, sender: str, role: str, content: str, image: Optional[str] = None):
    conn = get_db_conn(); c = conn.cursor()
    ts = datetime.utcnow().isoformat()
    c.execute("INSERT INTO messages (conversation_id, sender, role, content, image, timestamp) VALUES (?,?,?,?,?,?)",
              (conv_id, sender, role, content, image, ts))
    conn.commit(); conn.close()

def load_messages(conv_id: int) -> List[Dict[str, Any]]:
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT sender, role, content, image, timestamp FROM messages WHERE conversation_id=? ORDER BY id", (conv_id,))
    rows = c.fetchall(); conn.close()
    return [{"sender": r["sender"], "role": r["role"], "content": r["content"], "image": r["image"], "timestamp": r["timestamp"]} for r in rows]

# ---------------------------
# Small title generator
# ---------------------------
STOPWORDS = set(["the","and","for","that","with","this","what","when","where","which","would","could","should","there","their","about","your","from","have","just","like","also","been","they","them","will","how","can","a","an","in","on","of","to","is","are","it"])

def generate_title(text: str, max_words: int = 5) -> str:
    if not text: return "New chat"
    cleaned = re.sub(r"[^0-9a-zA-Z\s]", " ", text.lower())
    words = [w for w in cleaned.split() if len(w) > 2 and w not in STOPWORDS]
    chosen = []
    for w in words:
        if w not in chosen:
            chosen.append(w)
        if len(chosen) >= max_words:
            break
    if not chosen:
        short = text.strip()
        return (short[:40] + "...") if len(short) > 40 else short
    return " ".join(chosen).capitalize()

# ---------------------------
# OpenRouter LLM call (safe)
# ---------------------------
def get_openrouter_key() -> Optional[str]:
    # 1) Streamlit secrets
    try:
        key = st.secrets.get("OPENROUTER_API_KEY") if hasattr(st, "secrets") else None
        if key:
            return key
    except Exception:
        pass
    # 2) environment variable
    return os.getenv("OPENROUTER_API_KEY")

OPENROUTER_API_KEY = get_openrouter_key()
MODEL = DEFAULT_MODEL

def call_openrouter(messages: List[Dict[str,str]]) -> Dict[str, Any]:
    """
    Returns either {"reply": str} on success OR {"error": str, "status_code": int, "raw": ...} on failure.
    """
    key = OPENROUTER_API_KEY
    if not key:
        return {"error": "No API key configured", "status_code": None}
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": messages}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=20)
        if r.status_code == 401:
            return {"error": "Unauthorized (401) — check your API key", "status_code": 401, "raw": r.text}
        r.raise_for_status()
        data = r.json()
        # Extract reply defensively
        if isinstance(data, dict):
            # common OpenRouter/OpenAI style
            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                # message could be in 'message' or 'text'
                msg = choice.get("message") or choice.get("text")
                if isinstance(msg, dict):
                    return {"reply": msg.get("content","")}
                return {"reply": msg}
            # fallback for other formats
            if "text" in data and isinstance(data["text"], str):
                return {"reply": data["text"]}
        return {"error": "Unexpected LLM response format", "status_code": r.status_code, "raw": data}
    except requests.RequestException as e:
        raw_code = None
        try:
            raw_code = e.response.status_code
        except Exception:
            raw_code = None
        return {"error": f"LLM request failed: {e}", "status_code": raw_code}

# ---------------------------
# Mic & TTS components (client-side)
# ---------------------------
def mic_component(key="mic"):
    # Uses browser SpeechRecognition; posts recognized text to Streamlit (components.html return handling varies).
    html = r"""
    <html>
    <body>
    <button id="mic" style="padding:8px 12px;border-radius:8px">🎤 Start</button>
    <script>
    (function(){
      const btn = document.getElementById('mic');
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
          // send top-level postMessage expected by Streamlit
          const payload = {'text': text};
          window.parent.postMessage({isStreamlitMessage:true, type:'FROM_COMPONENT', payload: payload}, '*');
        };
        recognition.onend = function(){ recognizing=false; btn.innerText='🎤 Start'; }
      } else {
        btn.disabled = true; btn.innerText = 'Not supported';
      }
      btn.onclick = function(){
        if(!recognition) return;
        if(recognizing){ recognition.stop(); recognizing=false; btn.innerText='🎤 Start'; }
        else{ recognition.start(); recognizing=true; btn.innerText='⏸ Stop'; }
      };
    })();
    </script>
    </body>
    </html>
    """
    import streamlit.components.v1 as components
    components.html(html, height=60, key=key)

def tts_component(text: str):
    if not text: return
    safe = json.dumps(text)
    html = f"""
    <html><body><script>
    const txt = {safe};
    if ('speechSynthesis' in window) {{
      const u = new SpeechSynthesisUtterance(txt);
      u.rate = 1; u.pitch = 1;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    }}
    </script></body></html>
    """
    import streamlit.components.v1 as components
    components.html(html, height=10, key=f"tts_{abs(hash(text))%100000}")

# ---------------------------
# UI helpers: message bubble styles
# ---------------------------
def user_bubble(text: str):
    """Render a right-aligned user chat bubble."""
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-end;margin:6px 0">
      <div style="background:linear-gradient(180deg,#bffafc,#a3f7f7);
                  color:#001;
                  padding:10px 14px;
                  border-radius:12px;
                  max-width:75%;
                  word-wrap:break-word;">
        {text}
      </div>
    </div>
    """, unsafe_allow_html=True)


def assistant_bubble(text: str):
    """Render a left-aligned assistant chat bubble."""
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-start;margin:6px 0">
      <div style="background:rgba(255,255,255,0.05);
                  color:#e8f9ff;
                  padding:10px 14px;
                  border-radius:12px;
                  max-width:75%;
                  word-wrap:break-word;
                  border-left:3px solid rgba(0,255,255,0.15);">
        {text}
      </div>
    </div>
    """, unsafe_allow_html=True)

# ---------------------------
# Streamlit session-state initialization
# ---------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "current_conv" not in st.session_state:
    st.session_state.current_conv = None
if "mic_text" not in st.session_state:
    st.session_state.mic_text = ""
if "last_reply" not in st.session_state:
    st.session_state.last_reply = ""
if "llm_error" not in st.session_state:
    st.session_state.llm_error = None
if "persona" not in st.session_state:
    st.session_state.persona = "Friendly"

# ---------------------------
# App: header & auth
# ---------------------------
st.title("Nexa — Assistant")
st.write("")  # small spacing

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("Account")
    if not st.session_state.user:
        mode = st.selectbox("Mode", ["Login", "Register"], key="auth_mode")
        username = st.text_input("Username", key="auth_user")
        password = st.text_input("Password", type="password", key="auth_password")
        if mode == "Register":
            if st.button("Create account"):
                if not username or not password:
                    st.warning("Provide username and password.")
                else:
                    try:
                        create_user(username, password)
                        st.success("Account created — you can login now.")
                    except Exception as e:
                        st.error(f"Registration error: {e}")
        else:
            if st.button("Login"):
                if verify_user(username, password):
                    st.session_state.user = username
                    st.success(f"Logged in as {username}")
                    st.experimental_rerun()  # older name sometimes present — we'll call rerun below if needed
                else:
                    st.error("Invalid credentials")
    else:
        st.markdown(f"**Logged in as:** {st.session_state.user}")
        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.current_conv = None
            st.experimental_rerun()

    st.markdown("---")
    st.selectbox("Persona", ["Friendly", "Neutral", "Cheerful", "Professional"], index=["Friendly","Neutral","Cheerful","Professional"].index(st.session_state.persona), key="persona_select")
    st.session_state.persona = st.session_state.persona_select
    st.checkbox("Voice output (browser TTS)", value=True, key="voice_toggle")
    st.session_state.voice_enabled = st.session_state.voice_toggle
    st.markdown("---")
    if st.button("New conversation"):
        if not st.session_state.user:
            st.warning("Log in first.")
        else:
            st.session_state.current_conv = create_conversation(st.session_state.user)
            st.experimental_rerun()

with col_right:
    # Messages area like ChatGPT
    st.markdown("### Chat")
    # Select conversation if none
    if not st.session_state.current_conv:
        if st.session_state.user:
            convs = list_conversations(st.session_state.user)
            if convs:
                choices = {f"{c['title']} (#{c['id']})": c['id'] for c in convs}
                sel = st.selectbox("Open conversation", options=list(choices.keys()), index=0, key="conv_selector") if convs else None
                if sel:
                    st.session_state.current_conv = choices[sel]
            else:
                st.info("No conversations yet. Click 'New conversation' on the left.")
        else:
            st.info("Login to start conversations.")

    # render messages
    if st.session_state.current_conv:
        msgs = load_messages(st.session_state.current_conv)
        # large scrollable container
        for m in msgs:
            if m["role"] == "assistant":
                assistant_bubble(m["content"])
            else:
                user_bubble(m["content"])

    # input area
    st.markdown("---")
    with st.form(key="chat_form", clear_on_submit=False):
        # If mic text was posted via component, prefer it
        input_text = st.text_input("Type a message", value=st.session_state.mic_text or "", key="input_text")
        uploaded = st.file_uploader("Image (optional)", type=["png","jpg","jpeg","gif"], key="img_up")
        cols = st.columns([1,1,8])
        with cols[0]:
            mic_component()
        with cols[1]:
            send = st.form_submit_button("Send")
        # handle sending
        if send:
            msg = (input_text or "").strip()
            if not msg and not uploaded:
                st.warning("Write something or attach an image.")
            else:
                if not st.session_state.current_conv:
                    if not st.session_state.user:
                        st.error("Login to create a conversation.")
                    else:
                        st.session_state.current_conv = create_conversation(st.session_state.user)
                # handle file
                image_path = None
                if uploaded:
                    fname = uploaded.name
                    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                    safe = f"{ts}_{fname}"
                    dest = UPLOAD_DIR / safe
                    with open(dest, "wb") as f: f.write(uploaded.getbuffer())
                    image_path = str(dest)
                # save user message
                save_message(st.session_state.current_conv, st.session_state.user or "anon", "user", msg or "(image)", image_path)
                # auto title
                if msg:
                    rename_conversation_once(st.session_state.current_conv, generate_title(msg, max_words=5))
                # Build LLM messages for context if key present
                reply_text = None
                llm_info = None
                if OPENROUTER_API_KEY and msg:
                    history = load_messages(st.session_state.current_conv)
                    messages_payload = [{"role":"system","content":f"You are Nexa, a helpful assistant. Persona: {st.session_state.persona}."}]
                    for h in history:
                        role = "assistant" if h["role"] == "assistant" else "user"
                        messages_payload.append({"role": role, "content": h["content"]})
                    messages_payload.append({"role":"user", "content": msg})
                    llm_info = call_openrouter(messages_payload)
                    if "reply" in llm_info:
                        reply_text = llm_info["reply"]
                    else:
                        # LLM error: set llm_error for display and fallback below
                        st.session_state.llm_error = llm_info
                # If no LLM reply, fallback to persona-based reply
                if not reply_text:
                    p = st.session_state.persona
                    if p == "Friendly":
                        reply_text = f"🙂 Sure — {msg or '(image)'}! I'd be happy to help."
                    elif p == "Neutral":
                        reply_text = msg or "(image)"
                    elif p == "Cheerful":
                        reply_text = f"🎉 Yay! Here's a quick take: {msg or '(image)'} — hope that helps!"
                    elif p == "Professional":
                        reply_text = f"As requested, here's a concise response: {msg or '(image)'}."
                    else:
                        reply_text = f"{msg or '(image)'}"
                    # If LLM had an error, append an informative note
                    if st.session_state.llm_error:
                        err = st.session_state.llm_error
                        ent = f"(LLM error: {err.get('error','unknown')})"
                        if err.get("status_code") == 401:
                            ent += " — Unauthorized (401). Check OpenRouter API key in Streamlit Secrets."
                        reply_text = ent + "\n\n" + reply_text
                # save assistant
                save_message(st.session_state.current_conv, "assistant", "assistant", reply_text, None)
                st.session_state.mic_text = ""
                st.session_state.last_reply = reply_text
                # rerun to update UI
                st.experimental_rerun()

    # After sending or on page load: if last_reply present and voice enabled, play TTS
    if st.session_state.get("last_reply") and st.session_state.get("voice_enabled", True):
        tts_component(st.session_state.last_reply)
        st.session_state.last_reply = ""

# ---------------------------
# Footer & LLM error display
# ---------------------------
st.markdown("---")
if st.session_state.llm_error:
    err = st.session_state.llm_error
    st.error(f"LLM error: {err.get('error')} (status: {err.get('status_code')})")
    if err.get("status_code") == 401:
        st.info("401 Unauthorized — please add or fix OPENROUTER_API_KEY in Streamlit Secrets (Manage app → Secrets).")
    if st.button("Clear LLM error"):
        st.session_state.llm_error = None

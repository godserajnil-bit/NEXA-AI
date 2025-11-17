# Nexa_Streamlit.py
# Option A: Full Nexa UI — stable Streamlit layout, sidebar, mic, DB, LLM wrapper, single form, st.rerun()
import sys, io, os, sqlite3, requests, html
from datetime import datetime, timezone
import streamlit as st
import streamlit.components.v1 as components

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
# Database helpers (unchanged logic)
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
    t = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO conversations (user, title, created_at) VALUES (?, ?, ?)", (username, title, t))
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
    t = datetime.now(timezone.utc).isoformat()
    c.execute("""INSERT INTO messages (conversation_id, sender, role, content, created_at)
                 VALUES (?, ?, ?, ?, ?)""", (cid, sender, role, content, t))
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
# LLM wrapper (OpenRouter)
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
# Minimal CSS (safe)
# --------------------
st.markdown(
    """
    <style>
      /* container sizing left visual + center chat */
      .nexa-left {
          display:flex; align-items:center; justify-content:center;
          width:72px; height:72px; border-radius:12px;
          background: rgba(255,255,255,0.04); font-weight:800;
      }
      .chat-user { background:#14a37f; color:#001b12; padding:10px 14px; border-radius:12px; margin:8px 0; max-width:80%; margin-left:auto; }
      .chat-ai { background:#07101a; color:#dff5ee; padding:10px 14px; border-radius:12px; margin:8px 0; max-width:80%; margin-right:auto; }
      .welcome { color:#cfe8ee; margin-top:8px; }
      .mic-circle { width:44px; height:44px; border-radius:50%; display:flex;align-items:center;justify-content:center; background:#0b1220; color:#cfe8ee; border:1px solid rgba(255,255,255,0.04); cursor:pointer; }
      .controls { display:flex; gap:8px; align-items:center; width:100%; }
      .inputbox { flex:1; }
    </style>
    """, unsafe_allow_html=True
)

# --------------------
# Session init
# --------------------
if "user" not in st.session_state:
    st.session_state.user = "You"
if "conv_id" not in st.session_state:
    st.session_state.conv_id = create_conversation(st.session_state.user)
if "speak_on_reply" not in st.session_state:
    st.session_state.speak_on_reply = False

# --------------------
# Sidebar (Streamlit sidebar for stability)
# --------------------
with st.sidebar:
    st.markdown("## 🟦 Nexa")
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
                st.rerun()
    else:
        st.info("No conversations yet — press New Chat to start.")

    if st.button("➕ New Chat"):
        st.session_state.conv_id = create_conversation(st.session_state.user)
        st.rerun()

    if st.button("🧹 Reset Database"):
        reset_db()
        st.session_state.conv_id = create_conversation(st.session_state.user)
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
# Main layout: left visual + chat area
# --------------------
left_col, center_col = st.columns([0.08, 0.92])

with left_col:
    st.markdown('<div class="nexa-left">N</div>', unsafe_allow_html=True)

with center_col:
    st.title("Nexa")
    st.markdown("Ask anything — use the mic or type below.")

    # show messages
    messages = load_messages(st.session_state.conv_id)
    if not messages:
        st.markdown('<div class="welcome">Welcome to Nexa — start the conversation.</div>', unsafe_allow_html=True)
    else:
        for m in messages:
            content = html.escape(m["content"])
            if m["role"] == "assistant":
                st.markdown(f"<div class='chat-ai'>{content}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='chat-user'>{content}</div>", unsafe_allow_html=True)

    st.markdown("")  # spacing

    # --------------------
    # Single form (mic + input + submit)
    # --------------------
    with st.form("nexa_input_form", clear_on_submit=True):
        cols = st.columns([0.06, 0.82, 0.12])
        with cols[0]:
            # microphone HTML (posts transcript to parent)
            mic_html = r"""
            <div style="display:flex;justify-content:center;">
              <button id="nexaMic" class="mic-circle" title="Speak">🎤</button>
            </div>
            <script>
            (function(){
              const btn = document.getElementById('nexaMic');
              if(!window.SpeechRecognition && !window.webkitSpeechRecognition){
                btn.disabled = true;
                return;
              }
              const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
              const rec = new SR();
              rec.lang='en-US'; rec.interimResults=false; rec.maxAlternatives=1;
              rec.onresult = e => {
                const text = e.results[0][0].transcript;
                window.parent.postMessage({type:'nexa_transcript', text:text}, '*');
              };
              btn.onclick = ()=>{ try{ rec.start(); setTimeout(()=>{ try{ rec.stop(); }catch(e){} },6000); }catch(e){} };
            })();
            </script>
            """
            components.html(mic_html, height=64)
        with cols[1]:
            user_text = st.text_input(
                "Message",
                placeholder="Ask Nexa...",
                key="nexa_input",
                label_visibility="collapsed"
            )
        with cols[2]:
            submitted = st.form_submit_button("Send")

    # JS listener to auto-fill input & auto-submit when mic provides transcript
    components.html(r"""
    <script>
    window.addEventListener('message', (ev)=>{
      if(!ev.data || ev.data.type!=='nexa_transcript') return;
      const text = ev.data.text||'';
      // try to find input by aria-label (label "Message" collapsed) or by data-testid
      const input = document.querySelector('input[aria-label="Message"]') || document.querySelector('input[data-testid="stTextInput-input"]') || document.querySelector('input[type="text"]');
      if(input){
        input.focus();
        input.value = text;
        input.dispatchEvent(new Event('input', {bubbles:true}));
        // try to click Send button
        setTimeout(()=>{
          const forms = document.querySelectorAll('form');
          for(const f of forms){
            const btn = f.querySelector('button[type="submit"], button');
            if(btn && /send/i.test(btn.innerText || '')) { btn.click(); break; }
          }
        }, 200);
      }
    });
    </script>
    """, height=0)

    # --------------------
    # Handle submission
    # --------------------
    if submitted and user_text and user_text.strip():
        text = user_text.strip()
        save_message(st.session_state.conv_id, st.session_state.user, "user", text)
        rename_conversation_if_default(st.session_state.conv_id, text.split("\n",1)[0][:40])

        history = [{"role":"system","content":"You are Nexa, a helpful assistant."}]
        for m in load_messages(st.session_state.conv_id):
            history.append({"role": m["role"], "content": m["content"]})

        with st.spinner("Nexa is thinking..."):
            reply = call_openrouter(history)
        save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

        if st.session_state.get("speak_on_reply", False):
            safe = html.escape(reply).replace("\n", " ")
            tts = f"<script>speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));</script>"
            components.html(tts, height=0)

        st.rerun()

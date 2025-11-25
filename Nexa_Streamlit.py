# Nexa_Streamlit.py
# Combined final: Nexa UI with logo+quote top-center (disappear on typing), DB, mic, LLM wrapper, sidebar black, light-grey chat
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
/* Sidebar background black */
[data-testid="stSidebar"] > div:first-child {
  background-color: #000000;
  color: #ffffff;
}

/* Main background light grey */
.reportview-container .main .block-container {
  background: #e6e6e6;
}

/* Chat bubbles */
.chat-user { background:#cfe3ff; padding:10px 12px; border-radius:12px; margin:8px 0; max-width:78%; margin-left:auto; }
.chat-ai { background:#ffffff; padding:10px 12px; border-radius:12px; margin:8px 0; max-width:78%; margin-right:auto; }

/* intro area */
#nexa-intro { text-align:center; margin-top:6px; margin-bottom:14px; }
#nexa-logo { width:72px; height:auto; display:block; margin:0 auto 8px auto; }
#nexa-quote { color:#333; font-style:italic; }

/* input rounded */
input[data-testid="stTextInput"] { border-radius:24px !important; padding:10px !important; }
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
# Mic + Input form (single form, no missing-submit warnings)
# --------------------
with st.form("nexa_input_form", clear_on_submit=True):
    cols = st.columns([0.06, 0.82, 0.12])
    with cols[0]:
        # Mic button — posts transcript back to Streamlit via parent message
        mic_html = r"""
        <div style="display:flex;justify-content:center;">
          <button id="nexaMic" title="Speak" style="width:44px;height:44px;border-radius:50%;">🎤</button>
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
        user_text = st.text_input("Message", placeholder="Ask Nexa...", key="nexa_input", label_visibility="collapsed")
    with cols[2]:
        submitted = st.form_submit_button("Send")

# JS listener to auto-fill input & auto-submit when mic posts transcript,
# and to hide the intro (logo+quote) immediately on typing (client-side).
components.html(r"""
<script>
window.addEventListener('message', (ev)=>{
  if(!ev.data) return;
  // mic transcript
  if(ev.data.type === 'nexa_transcript'){
    const text = ev.data.text || '';
    const input = document.querySelector('input[aria-label="Message"]') || document.querySelector('input[type="text"]');
    if(input){ input.focus(); input.value = text; input.dispatchEvent(new Event('input', {bubbles:true})); }
    // try to click send
    setTimeout(()=>{ 
      const forms = document.querySelectorAll('form');
      for(const f of forms){
        const btn = f.querySelector('button[type="submit"], button');
        if(btn && /send/i.test(btn.innerText || '')) { btn.click(); break; }
      }
    }, 200);
  }
});
// hide intro on typing
(function(){
  const input = document.querySelector('input[aria-label="Message"]') || document.querySelector('input[type="text"]');
  const hideIntro = ()=>{
    try{
      const intro = window.parent.document.getElementById('nexa-intro');
      if(intro) intro.style.display = 'none';
      // also inform Streamlit server by setting a hidden anchor and clicking (no server-side here)
    }catch(e){}
  };
  if(input){
    input.addEventListener('input', hideIntro);
  }
})();
</script>
""", height=0)

# --------------------
# Handle submit server-side (store message, call LLM, TTS optional)
# --------------------
if submitted and user_text and user_text.strip():
    text = user_text.strip()
    save_message(st.session_state.conv_id, st.session_state.user, "user", text)
    # rename conversation if it had default title
    rename_conversation_if_default(st.session_state.conv_id, text.split("\n",1)[0][:40])
    # hide intro for server rendering too
    st.session_state.show_intro = False

    # build history payload
    history = [{"role":"system","content":"You are Nexa, a helpful assistant."}]
    for m in load_messages(st.session_state.conv_id):
        history.append({"role": m["role"], "content": m["content"]})

    with st.spinner("Nexa is thinking..."):
        reply = call_openrouter(history)

    save_message(st.session_state.conv_id, "Nexa", "assistant", reply)

    # optional: browser TTS if enabled
    if st.session_state.get("speak_on_reply", False):
        safe = html.escape(reply).replace("\n", " ")
        tts_script = f"<script>speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance('{safe}'));</script>"
        components.html(tts_script, height=0)

    # rerun so UI shows new messages and intro hidden
    st.rerun()

# End — keep code intact, DB persists history across refreshes

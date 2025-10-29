# Nexa_Final_Combined.py
# Final combined single-file Flask app — includes requested features and cinematic "nexa" splash.
# Usage:
#   pip install flask requests werkzeug
#   python Nexa_Final_Combined.py
#   Open http://127.0.0.1:5000

import os
import re
import sqlite3
import webbrowser
from datetime import datetime, timedelta
from flask import (
    Flask, request, jsonify, session, redirect, url_for,
    send_from_directory, make_response, render_template_string
)
from werkzeug.security import generate_password_hash, check_password_hash
import requests

# ---------------------------
# Configuration
# ---------------------------
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.permanent_session_lifetime = timedelta(days=30)

DB_FILE = "nexa_final.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# API key placeholders (kept blank if you don't want to call external APIs)
OPENROUTER_API_KEY = "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"   # <- add your openrouter / openai key here for LLM integration
GNEWS_API_KEY = "38bcd24319a1b6111822f07fa5fc3bc8"        # <- optional GNews key

MODEL = "gpt-4o-mini"     # placeholder

# ---------------------------
# Database utilities
# ---------------------------
def get_db_conn():
    conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_conn()
    c = conn.cursor()
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
    conn.commit()
    conn.close()

init_db()

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
# Auth helpers
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
    if not GNEWS_API_KEY:
        return f"(No news API key) You searched: {query}"
    try:
        url = f"https://gnews.io/api/v4/search?q={requests.utils.requote_uri(query)}&token={GNEWS_API_KEY}&lang=en&max={max_results}"
        r = requests.get(url, timeout=8); r.raise_for_status()
        arts = r.json().get("articles", [])
        if not arts: return "No news found."
        items = [f"• {a.get('title','No title')} ({a.get('source',{}).get('name','source')})" for a in arts]
        return "\n".join(items)
    except Exception as e:
        return f"News fetch error: {e}"

# ---------------------------
# Serve uploads
# ---------------------------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)

# ---------------------------
# HTML / CSS / JS Template (single-file)
# ---------------------------
INDEX_HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nexa — Assistant</title>
<style>
/* ---------- core theme ---------- */
:root{--accent:#00f0ff;--muted:#9fb8c9;--bg:#0a0b10;--panel:rgba(255,255,255,0.02)}
*{box-sizing:border-box}
html,body{height:100%;margin:0;font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;background:
 radial-gradient(1200px 400px at 10% 10%, rgba(255,230,200,0.06), transparent 10%),
 radial-gradient(1000px 400px at 90% 90%, rgba(241,211,255,0.04), transparent 10%),
 linear-gradient(180deg,#06070a 0%, var(--bg) 60%); color:#fff;}

/* ---------- layout ---------- */
.app{display:grid;grid-template-columns:320px 1fr;gap:0;height:100vh;align-items:stretch}
.sidebar{background:linear-gradient(180deg, rgba(0,0,0,0.6), rgba(0,0,0,0.7)); border-right:3px solid rgba(255,255,255,0.04); padding:18px; display:flex;flex-direction:column; gap:14px}
.brand{font-weight:800;color:var(--accent);text-align:center;padding:8px 0;font-size:18px}
.brand-splash{width:84px;height:84px;margin:0 auto 8px;background:url('https://i.imgur.com/ObRj9jD.png') center/contain no-repeat}
.left-actions{display:flex;flex-direction:column;gap:8px}
.action-btn{padding:10px;border-radius:10px;border:1px solid rgba(255,255,255,0.04); background:transparent;color:#fff;cursor:pointer;text-align:left}
.conversations{flex:1;overflow:auto;padding-top:8px;display:flex;flex-direction:column;gap:8px;scrollbar-width:thin}
.conv-item{padding:12px;border-radius:10px;background:transparent;color:#fff;cursor:pointer;font-size:14px;border:1px solid rgba(255,255,255,0.02);display:flex;justify-content:space-between;align-items:center}
.conv-item:hover{background:rgba(255,255,255,0.02)}
.conv-title-text{flex:1;padding-right:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.conv-controls{display:flex;gap:6px}

/* ---------- main ---------- */
.main{display:flex;flex-direction:column;height:100vh}
.header{display:flex;align-items:center;justify-content:space-between;padding:16px;border-bottom:1px solid rgba(255,255,255,0.02)}
.title{font-weight:700;color:#fff;font-size:18px}
.header-right{display:flex;gap:8px;align-items:center}
.small-btn{padding:8px;border-radius:8px;border:1px solid rgba(255,255,255,0.04);background:transparent;color:#fff;cursor:pointer}

/* ---------- chat panel ---------- */
.chat-panel{margin:20px;border-radius:14px;flex:1;display:flex;flex-direction:column;background:linear-gradient(180deg, rgba(255,255,255,0.015), rgba(255,255,255,0.008)); border:1px solid rgba(255,255,255,0.02); padding:18px; overflow:hidden; position:relative}
.messages{flex:1;overflow:auto;padding:20px 12px;display:flex;flex-direction:column;gap:14px}
.msg-row{display:flex;max-width:80%}
.msg-row.user{margin-left:auto;justify-content:flex-end}
.bubble{padding:12px 14px;border-radius:12px;line-height:1.45;font-size:15px;word-break:break-word;max-width:72%}
.bubble.user{background:linear-gradient(180deg, rgba(0,255,255,0.08), rgba(0,255,255,0.04));color:#001;border:1px solid rgba(0,255,255,0.08)}
.assistant-text{padding:8px 10px;border-radius:8px; background:transparent;color:#dff9ff; border-left:3px solid rgba(255,255,255,0.03); font-size:15px;max-width:78%}

/* images */
.message-image{max-width:360px;border-radius:8px;margin-top:8px;display:block}

/* input */
.input-area{display:flex;gap:8px;padding:12px;align-items:center;border-top:1px solid rgba(255,255,255,0.02)}
.input{flex:1;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,0.04);background:transparent;color:#fff;font-size:15px}
.icon-btn{padding:10px;border-radius:8px;border:none;cursor:pointer;background:transparent;color:#fff;font-size:18px}
.send-btn{padding:10px 14px;border-radius:8px;border:none;background:var(--accent);color:#001;cursor:pointer;font-weight:700}

/* suggestions overlay */
.suggestions{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none;transition:opacity 0.25s ease}
.suggestions-inner{pointer-events:auto;text-align:center;color:#fff;background:transparent}
.suggestions-title{font-size:28px;font-weight:700;margin-bottom:10px}
.suggestions-grid{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}
.sugg-card{background:rgba(255,255,255,0.03);padding:12px 16px;border-radius:10px;min-width:220px;max-width:320px;font-size:15px;cursor:pointer}

/* cinematic splash showing the word "nexa" */
#splash{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:linear-gradient(180deg, rgba(0,0,0,0.85), rgba(0,0,0,0.9));z-index:9999}
#splash .nexa-logo{font-weight:900;font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;color:transparent;
 background: linear-gradient(90deg, #00f0ff, #8be9ff, #b9b6ff);
 -webkit-background-clip: text; background-clip: text;
 font-size:88px; letter-spacing:4px; text-transform:lowercase;
 filter:drop-shadow(0 8px 20px rgba(0,240,255,0.14));
 transform:scale(0.7); opacity:0;
 animation: cinematic-pop 1200ms cubic-bezier(.18,.9,.22,1) forwards;
}
@keyframes cinematic-pop {
  0% { transform:scale(0.6) rotate(-6deg); opacity:0; filter:blur(6px) drop-shadow(0 6px 12px rgba(0,240,255,0.06)); }
  40% { transform:scale(1.08) rotate(2deg); opacity:1; filter:blur(0px) drop-shadow(0 12px 30px rgba(0,240,255,0.18)); }
  100% { transform:scale(1) rotate(0deg); opacity:1; filter:blur(0px) drop-shadow(0 18px 40px rgba(0,240,255,0.16)); }
}

/* responsive */
@media (max-width:900px){.app{grid-template-columns:1fr}.sidebar{display:none}}
</style>
</head>
<body>
<!-- Cinematic "nexa" splash overlay -->
<div id="splash"><div class="nexa-logo">nexa</div></div>

<div class="app" id="appRoot" style="visibility:hidden">
  <div class="sidebar" role="navigation" aria-label="Sidebar">
    <div class="brand"><div class="brand-splash" aria-hidden="true"></div> Nexa — Assistant</div>

    <div class="left-actions">
      <button class="action-btn" onclick="createNew()">+ New chat</button>
      <button class="action-btn" onclick="openHistory()">History</button>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button id="voiceToggleLeft" class="action-btn" onclick="toggleVoiceOutput()">Voice: On</button>
        <button class="action-btn" onclick="togglePersona()">Persona</button>
      </div>
    </div>

    <div class="conversations" id="convList" aria-live="polite"></div>

    <div style="margin-top:8px;border-top:1px solid rgba(255,255,255,0.02);padding-top:8px">
      <div style="font-size:13px;color:#bcd">Logged in as: <strong id="userLabel"></strong></div>
      <div style="margin-top:8px"><button class="action-btn" onclick="logout()">Log out</button></div>
    </div>
  </div>

  <div class="main">
    <div class="header">
      <div>
        <div class="title" id="convTitle">Welcome to Nexa</div>
        <div style="font-size:12px;color:#9fb8c9">Replica UI — white text, dark theme</div>
      </div>
      <div class="header-right">
        <select id="personaSelect" onchange="setPersona(this.value)" style="padding:8px;border-radius:8px;background:#111;color:#fff;border:1px solid rgba(255,255,255,0.04)">
          <option>Friendly</option><option>Neutral</option><option>Cheerful</option><option>Professional</option>
        </select>
        <button class="small-btn" onclick="renameCurrent()">Rename</button>
        <button class="small-btn" onclick="deleteCurrent()">Delete</button>
      </div>
    </div>

    <div class="chat-panel" id="chatPanel">
      <div class="messages" id="messages" role="log" aria-live="polite"></div>

      <div class="suggestions" id="suggestionsOverlay" aria-hidden="false" style="opacity:1;">
        <div class="suggestions-inner" id="suggestionsInner">
          <div class="suggestions-title">Try these</div>
          <div class="suggestions-grid" id="suggestionsGrid"></div>
          <div style="margin-top:8px;font-size:12px;color:var(--muted)">Examples • Capabilities • Limitations</div>
        </div>
      </div>

      <div class="input-area" aria-label="Message input">
        <input id="userInput" class="input" placeholder="Ask Nexa..." aria-label="Message" autocomplete="off" />
        <input id="fileInput" type="file" accept="image/*" style="display:none" />
        <button class="icon-btn" title="Attach image" onclick="document.getElementById('fileInput').click()">➕</button>
        <button id="micBtn" class="icon-btn" title="Voice input" onclick="toggleVoiceRecognition()">🎤</button>
        <button class="send-btn" onclick="sendMessage()">Send</button>
      </div>
    </div>
  </div>
</div>

<script>
/* --------------- Client logic --------------- */
/* Global state */
let currentConv = null;
let voiceOutputEnabled = true;     // client state, synced with server
let recognition = null;
let recognizing = false;
let persona = 'Friendly';
const suggestionsPool = [
  "Explain quantum computing in simple terms",
  "Write a poem about rain in 4 lines",
  "How do I make an HTTP request in JavaScript?",
  "Give me ideas for a 10 year old's birthday",
  "Help me debug a Python error",
  "Summarize the latest news about technology",
  "Create a grocery list for a week",
  "Plan a 3-day itinerary for Paris"
];

/* Splash handling (cinematic 'nexa' logo) */
window.addEventListener('load', () => {
  // show splash for 900ms then reveal app with fade
  setTimeout(()=> {
    const splash = document.getElementById('splash');
    splash.style.transition = 'opacity 450ms ease';
    splash.style.opacity = '0';
    setTimeout(()=>{ splash.remove(); document.getElementById('appRoot').style.visibility='visible'; }, 480);
  }, 900);

  // Initialize app after splash (load user/conversations)
  setTimeout(initApp, 950);
});

/* Initialize app */
function initApp(){
  fetch('/whoami').then(r=>r.json()).then(j=>{ if(j.user) document.getElementById('userLabel').textContent = j.user; });
  loadConversations();
  loadPersona();
  loadVoiceFromServer();
  showRandomSuggestions();
  setInterval(()=>{ if(!isSuggestionsDismissed()) showRandomSuggestions(); }, 9000);

  // input send on Enter
  const input = document.getElementById('userInput');
  input.addEventListener('keydown', (e)=>{ if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); sendMessage(); } else { /* typing: hide suggestions */ dismissSuggestions(); } });

  // file input
  document.getElementById('fileInput').addEventListener('change', (e)=>{ const f = e.target.files[0]; if(f){ const url = URL.createObjectURL(f); addMessageToUI('[Image attached]', 'user', url); }});
}

/* Suggestions */ 
function isSuggestionsDismissed(){ return localStorage.getItem('nexa_suggestions_dismissed') === '1'; }
function dismissSuggestions(){ localStorage.setItem('nexa_suggestions_dismissed','1'); hideSuggestions(); }
function allowSuggestionsAgain(){ localStorage.removeItem('nexa_suggestions_dismissed'); }
function showRandomSuggestions(){
  const msgs = document.getElementById('messages');
  if(currentConv && msgs && msgs.children.length > 0) return hideSuggestions();
  if(isSuggestionsDismissed()) return hideSuggestions();
  const grid = document.getElementById('suggestionsGrid'); grid.innerHTML = '';
  const shuffled = suggestionsPool.slice().sort(()=>Math.random()-0.5);
  const chosen = shuffled.slice(0,3);
  chosen.forEach(s=>{ const d = document.createElement('div'); d.className = 'sugg-card'; d.textContent = s; d.onclick = ()=>{ document.getElementById('userInput').value = s; sendMessage(); hideSuggestions(); dismissSuggestions(); }; grid.appendChild(d); });
  const overlay = document.getElementById('suggestionsOverlay'); overlay.style.display='flex'; overlay.style.opacity='1';
}
function hideSuggestions(){ const overlay = document.getElementById('suggestionsOverlay'); overlay.style.opacity = '0'; setTimeout(()=>{ overlay.style.display='none'; }, 260); }

/* Voice recognition (mic) */
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.continuous = false;
  recognition.onresult = function(e){ const text = e.results[0][0].transcript; document.getElementById('userInput').value = text; sendMessage(); };
  recognition.onend = function(){ recognizing = false; document.getElementById('micBtn').innerText = '🎤'; };
}
function toggleVoiceRecognition(){
  if(!recognition){ alert('Voice recognition not supported in this browser.'); return; }
  if(recognizing){ recognition.stop(); recognizing=false; document.getElementById('micBtn').innerText='🎤'; }
  else{ recognition.start(); recognizing=true; document.getElementById('micBtn').innerText='⏸'; }
}

/* Voice output (TTS) persisted on server, immediate stop when toggled off */
function loadVoiceFromServer(){
  fetch('/get_voice').then(r=>r.json()).then(j=>{ voiceOutputEnabled = !!j.voice; updateVoiceToggleLeft(); });
}
function toggleVoiceOutput(){
  voiceOutputEnabled = !voiceOutputEnabled;
  updateVoiceToggleLeft();
  // persist server-side
  fetch('/set_voice', {method:'POST', body: new URLSearchParams({voice: voiceOutputEnabled ? '1' : '0'})});
  // immediate stop when toggled off
  if(!voiceOutputEnabled && 'speechSynthesis' in window) { window.speechSynthesis.cancel(); }
}
function updateVoiceToggleLeft(){ const el = document.getElementById('voiceToggleLeft'); el.innerText = 'Voice: ' + (voiceOutputEnabled ? 'On' : 'Off'); }

/* Persona handling (different reply logic per persona) */
function loadPersona(){ fetch('/get_persona').then(r=>r.json()).then(j=>{ persona = j.persona || 'Friendly'; document.getElementById('personaSelect').value = persona; }); }
function setPersona(p){ persona = p; fetch('/set_persona', {method:'POST', body: new URLSearchParams({persona: p})}); }
function togglePersona(){ const sel = document.getElementById('personaSelect'); const next = sel.value === 'Friendly' ? 'Neutral' : sel.value === 'Neutral' ? 'Cheerful' : sel.value === 'Cheerful' ? 'Professional' : 'Friendly'; sel.value = next; setPersona(next); }

/* Conversations list */
async function loadConversations(){
  const res = await fetch('/conversations'); const list = await res.json();
  const container = document.getElementById('convList'); container.innerHTML = '';
  list.forEach(item=>{
    const el = document.createElement('div'); el.className = 'conv-item';
    const left = document.createElement('div'); left.className = 'conv-title-text'; left.textContent = item.title || 'New chat';
    left.onclick = ()=> openConversation(item.id);
    const ctrls = document.createElement('div'); ctrls.className = 'conv-controls';
    const openBtn = document.createElement('button'); openBtn.className='small-icon'; openBtn.title='Open'; openBtn.innerText='⤴';
    openBtn.onclick = (ev)=>{ ev.stopPropagation(); openConversation(item.id); };
    const three = document.createElement('button'); three.className='small-icon'; three.title='More'; three.innerText='⋯';
    three.onclick = (ev)=>{ ev.stopPropagation(); showConvMenu(ev, item.id); };
    ctrls.appendChild(openBtn); ctrls.appendChild(three);
    el.appendChild(left); el.appendChild(ctrls); container.appendChild(el);
  });
}

/* Conversation menu */
function showConvMenu(ev, convId){
  ev.preventDefault();
  const menu = document.createElement('div');
  menu.style.position='fixed'; menu.style.left = ev.clientX + 'px'; menu.style.top = ev.clientY + 'px';
  menu.style.background = '#071018'; menu.style.border = '1px solid rgba(255,255,255,0.04)'; menu.style.padding = '8px'; menu.style.borderRadius = '6px'; menu.style.zIndex = 9999;
  const ren = document.createElement('div'); ren.style.padding='6px'; ren.style.cursor='pointer'; ren.innerText='Rename';
  ren.onclick = ()=>{ const t=prompt('New title:'); if(t){ fetch('/rename_conversation', {method:'POST', body:new URLSearchParams({id:convId, title:t})}).then(()=>{ loadConversations(); menu.remove(); }); } else menu.remove(); };
  const del = document.createElement('div'); del.style.padding='6px'; del.style.cursor='pointer'; del.innerText='Delete';
  del.onclick = ()=>{ if(confirm('Delete this conversation?')){ fetch('/delete_conversation', {method:'POST', body:new URLSearchParams({id:convId})}).then(()=>{ if(currentConv==convId){ currentConv=null; document.getElementById('messages').innerHTML=''; document.getElementById('convTitle').innerText='Welcome to Nexa'; allowSuggestionsAgain(); showRandomSuggestions(); } loadConversations(); menu.remove(); }); } else menu.remove(); };
  menu.appendChild(ren); menu.appendChild(del); document.body.appendChild(menu);
  const rm = ()=>{ if(menu) menu.remove(); document.removeEventListener('click',rm); }; setTimeout(()=>document.addEventListener('click',rm), 10);
}

/* Open conversation and load messages */
async function openConversation(id){
  currentConv = id;
  const info = await fetch('/conversation_info?id='+id).then(r=>r.json());
  if(info && info.title) document.getElementById('convTitle').innerText = info.title;
  const msgs = await fetch('/get_messages?conv='+id).then(r=>r.json());
  const msgCont = document.getElementById('messages'); msgCont.innerHTML = '';
  msgs.forEach(m => {
    // user messages appear as bubbles; assistant messages appear as plain assistant-text (per your request)
    if(m.role === 'assistant') addAssistantToUI(m.content, m.image);
    else addMessageToUI(m.content, m.role === 'user' ? 'user' : 'bot', m.image);
  });
  hideSuggestions();
}

/* Create / rename / delete conv */
async function createNew(){
  const res = await fetch('/new_conversation', {method:'POST'}); const j = await res.json();
  if(j.id){ currentConv = j.id; document.getElementById('convTitle').innerText = 'New chat'; document.getElementById('messages').innerHTML = ''; allowSuggestionsAgain(); showRandomSuggestions(); loadConversations(); }
}
async function renameCurrent(){
  if(!currentConv){ alert('Select a conversation first'); return; }
  const newTitle = prompt('Enter new title:'); if(!newTitle) return;
  await fetch('/rename_conversation', {method:'POST', body: new URLSearchParams({id: currentConv, title: newTitle})});
  loadConversations(); document.getElementById('convTitle').innerText = newTitle;
}
async function deleteCurrent(){
  if(!currentConv){ alert('Select a conversation first'); return; }
  if(!confirm('Delete this conversation?')) return;
  await fetch('/delete_conversation', {method:'POST', body: new URLSearchParams({id: currentConv})});
  currentConv = null; document.getElementById('messages').innerHTML = ''; document.getElementById('convTitle').innerText = 'Welcome to Nexa';
  allowSuggestionsAgain(); showRandomSuggestions(); loadConversations();
}

/* Add user bubble to UI */
function addMessageToUI(text, sender, image=null){
  const container = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'msg-row ' + (sender === 'user' ? 'user' : 'bot');
  const bubble = document.createElement('div');
  bubble.className = 'bubble ' + (sender === 'user' ? 'user' : 'bot');
  bubble.textContent = text || '';
  row.appendChild(bubble);
  if(image){
    const img = document.createElement('img'); img.src = image; img.className='message-image';
    bubble.appendChild(document.createElement('br')); bubble.appendChild(img);
  }
  container.appendChild(row); container.scrollTop = container.scrollHeight;
}

/* Add assistant text (no bubble framing) */
function addAssistantToUI(text, image=null){
  const container = document.getElementById('messages');
  const el = document.createElement('div');
  el.className = 'assistant-text';
  el.innerText = text || '';
  if(image){
    const img = document.createElement('img'); img.src = image; img.className='message-image';
    el.appendChild(document.createElement('br')); el.appendChild(img);
  }
  container.appendChild(el); container.scrollTop = container.scrollHeight;
}

/* Sending a message (file optional) */
async function sendMessage(){
  const input = document.getElementById('userInput');
  const text = (input.value || '').trim();
  const fileEl = document.getElementById('fileInput');
  const file = fileEl.files[0];
  if(!text && !file) return;

  // show user bubble immediately
  addMessageToUI(text || '[Image]', 'user', file ? URL.createObjectURL(file) : null);
  input.value = ''; fileEl.value = ''; dismissSuggestions();

  // show thinking placeholder
  const container = document.getElementById('messages');
  const trow = document.createElement('div'); trow.id = 'thinking'; trow.className = 'assistant-text'; trow.textContent = '...';
  container.appendChild(trow); container.scrollTop = container.scrollHeight;

  // prepare form
  const fd = new FormData(); fd.append('message', text);
  if(currentConv) fd.append('conv', currentConv);
  if(file) fd.append('image', file);

  try{
    const res = await fetch('/chat', {method:'POST', body: fd});
    const j = await res.json();
    const t = document.getElementById('thinking'); if(t) t.remove();

    // Per persona logic we implemented server-side returns appropriate reply, but we also handle TTS client-side
    if(j.reply) {
      addAssistantToUI(j.reply, j.image || null);
      // speak if enabled
      if(voiceOutputEnabled && j.reply && 'speechSynthesis' in window){
        const u = new SpeechSynthesisUtterance(j.reply);
        // adjust voice tone per persona (minor client-side tweak)
        if(persona === 'Cheerful'){ u.pitch = 1.2; u.rate = 1.05; }
        else if(persona === 'Professional'){ u.pitch = 0.95; u.rate = 0.95; }
        else { u.pitch = 1; u.rate = 1; }
        speechSynthesis.cancel(); // make sure no overlap
        speechSynthesis.speak(u);
      }
    }
    if(j.conv_id){ currentConv = j.conv_id; document.getElementById('convTitle').innerText = j.title || document.getElementById('convTitle').innerText; }
    loadConversations();
  }catch(err){
    const t = document.getElementById('thinking'); if(t) t.remove();
    addAssistantToUI('Error: ' + String(err), null);
  }
}

/* History & auth helpers */
function openHistory(){ window.location.href = '/history'; }
function logout(){ fetch('/logout').then(()=>window.location.href='/login'); }

/* ----------------- Misc helpers ----------------- */
/* when the user toggles voice off, we cancel any ongoing speechSynth immediately in toggleVoiceOutput above */

/* ----------------- initial load ----------------- */
</script>
</body>
</html>
"""

# ---------------------------
# Flask routes / API
# ---------------------------
@app.route("/whoami")
def whoami():
    return jsonify({"user": session.get("user")})

# Auth: login/register/logout
@app.route("/login", methods=["GET", "POST"])
def login_route():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        remember = bool(request.form.get("remember"))
        if verify_user(username, password):
            session["user"] = username
            session.permanent = True
            if "voice_enabled" not in session:
                session["voice_enabled"] = True
            resp = make_response(redirect(url_for("index")))
            if remember:
                resp.set_cookie("nexa_user", username, max_age=60*60*24*30)
            return resp
        else:
            return "<h3>Invalid credentials</h3><a href='/login'>Try again</a>"
    return """
    <html><head><meta name='viewport' content='width=device-width,initial-scale=1'>
    <style>body{background:#000;color:#fff;font-family:Inter;display:flex;justify-content:center;align-items:center;height:100vh}form{background:#111;padding:20px;border-radius:10px}</style></head><body>
    <form method='POST'><h2>Login</h2><input name='username' placeholder='Username' required><br><input type='password' name='password' placeholder='Password' required><br><label><input type='checkbox' name='remember'> Remember me</label><br><button>Login</button></form>
    <div style='margin-top:10px;color:#9fb8c9'>Or <a href='/register' style='color:#0ff'>register</a></div></body></html>
    """

@app.route("/register", methods=["GET", "POST"])
def register_route():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        if not username or not password:
            return "<h3>Missing fields</h3><a href='/register'>Back</a>"
        try:
            create_user(username, password)
            session["user"] = username; session.permanent = True; session["voice_enabled"] = True
            return redirect(url_for("index"))
        except Exception as e:
            return f"<h3>Error: {e}</h3><a href='/register'>Back</a>"
    return """
    <html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{background:#000;color:#fff;font-family:Inter;display:flex;justify-content:center;align-items:center;height:100vh}form{background:#111;padding:20px;border-radius:10px}</style></head><body>
    <form method='POST'><h2>Register</h2><input name='username' placeholder='Username' required><br><input type='password' name='password' placeholder='Password' required><br><button>Register</button></form>
    <div style='margin-top:10px;color:#9fb8c9'>Already registered? <a href='/login' style='color:#0ff'>Login</a></div></body></html>
    """

@app.route("/logout")
def logout_route():
    session.pop("user", None); session.pop("voice_enabled", None)
    resp = make_response(redirect(url_for("login_route"))); resp.set_cookie("nexa_user","",expires=0); return resp

# main UI
@app.route("/")
def index():
    if "user" not in session:
        cookie_user = request.cookies.get("nexa_user")
        if cookie_user:
            session["user"] = cookie_user; session.permanent = True; 
            if "voice_enabled" not in session: session["voice_enabled"] = True
        else:
            return redirect(url_for("login_route"))
    return render_template_string(INDEX_HTML)

# conversation endpoints
@app.route("/new_conversation", methods=["POST"])
def new_conversation_api():
    user = session.get("user")
    if not user: return jsonify({"error":"login required"}), 401
    conv_id = create_conversation(user)
    return jsonify({"id": conv_id})

@app.route("/conversations")
def conversations_api():
    user = session.get("user")
    if not user: return jsonify([])
    convs = list_conversations(user)
    return jsonify(convs)

@app.route("/conversation_info")
def conversation_info():
    user = session.get("user"); conv_id = request.args.get("id")
    if not user or not conv_id: return jsonify({"error":"missing"}), 400
    conn = get_db_conn(); c = conn.cursor(); c.execute("SELECT id, title FROM conversations WHERE id=? AND user=?", (conv_id, user))
    row = c.fetchone(); conn.close()
    if not row: return jsonify({"error":"not found"}), 404
    return jsonify({"id": row["id"], "title": row["title"]})

@app.route("/rename_conversation", methods=["POST"])
def rename_conv_api():
    user = session.get("user")
    if not user: return ("", 401)
    conv_id = request.form.get("id"); title = request.form.get("title")
    if not conv_id or not title: return ("", 400)
    conn = get_db_conn(); c = conn.cursor()
    c.execute("UPDATE conversations SET title=? WHERE id=? AND user=?", (title, conv_id, user))
    conn.commit(); conn.close()
    return ("", 200)

@app.route("/delete_conversation", methods=["POST"])
def delete_conv_api():
    user = session.get("user")
    if not user: return ("", 401)
    conv_id = request.form.get("id")
    if not conv_id: return ("", 400)
    delete_conversation(int(conv_id))
    return ("", 200)

@app.route("/get_messages")
def get_messages_api():
    user = session.get("user")
    if not user: return jsonify([])
    conv = request.args.get("conv")
    if not conv: return jsonify([])
    msgs = load_messages(int(conv))
    return jsonify(msgs)

# persona endpoints
@app.route("/set_persona", methods=["POST"])
def set_persona_api():
    if "user" not in session: return ("",401)
    persona = request.form.get("persona","Friendly"); session["persona"] = persona; return ("",200)

@app.route("/get_persona")
def get_persona_api():
    return jsonify({"persona": session.get("persona","Friendly")})

# voice preference endpoints
@app.route("/set_voice", methods=["POST"])
def set_voice_api():
    if "user" not in session: return ("",401)
    voice = request.form.get("voice","1"); session["voice_enabled"] = (voice == "1" or voice.lower()=="true"); return ("",200)

@app.route("/get_voice")
def get_voice_api():
    return jsonify({"voice": bool(session.get("voice_enabled", True))})

# chat endpoint (handles persona logic locally if OPENROUTER_API_KEY is blank)
@app.route("/chat", methods=["POST"])
def chat_api():
    user = session.get("user")
    if not user: return jsonify({"error":"login required"}), 401
    text = request.form.get("message","").strip()
    conv_id = request.form.get("conv")
    image_file = request.files.get("image")
    image_url = None
    if image_file and image_file.filename:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        safe_name = f"{user}_{ts}_{os.path.basename(image_file.filename)}"
        dest = os.path.join(UPLOAD_FOLDER, safe_name)
        image_file.save(dest)
        image_url = url_for('uploaded_file', filename=safe_name)

    if not conv_id:
        conv_id = create_conversation(user)
    else:
        conn = get_db_conn(); c = conn.cursor()
        c.execute("SELECT id FROM conversations WHERE id=? AND user=?", (conv_id, user))
        if not c.fetchone(): conv_id = create_conversation(user)
        conn.close()

    # Save the user message
    save_message(conv_id, user, "user", text, image_url)

    # Auto-generate title once
    if text:
        motive = simple_main_motive(text, max_words=5)
        rename_conversation_once(int(conv_id), motive)

    # If starts with "news:" handle via news helper
    reply = ""
    if text.lower().startswith("news:"):
        topic = text[5:].strip()
        reply = get_news(topic)
    else:
        # If API key is provided, attempt to call LLM via openrouter / openai compatible endpoint
        if OPENROUTER_API_KEY:
            try:
                headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
                history = load_messages(int(conv_id))
                messages = [{"role":"system","content":f"You are Nexa, a helpful assistant. Persona: {session.get('persona','Friendly')}."}]
                for m in history:
                    role = "assistant" if m["role"] == "assistant" else "user"
                    messages.append({"role": role, "content": m["content"]})
                messages.append({"role":"user","content": text})
                payload = {"model": MODEL, "messages": messages}
                r = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=18)
                r.raise_for_status()
                raw = r.json()
                reply = raw["choices"][0]["message"]["content"]
            except Exception as e:
                reply = f"(LLM error) {e}"
        else:
            # Local persona-driven reply logic (simple, deterministic)
            p = session.get("persona","Friendly")
            if p == "Friendly":
                # friendly: more verbose, empathetic
                reply = f"🙂 Sure — {text}. I'd be happy to help! Here's a friendly summary: {text}"
            elif p == "Neutral":
                # neutral: echo concisely
                reply = f"{text}"
            elif p == "Cheerful":
                # cheerful: upbeat and shorter
                reply = f"🎉 Yay! Quick take: {text} — hope that helps!"
            elif p == "Professional":
                # professional: concise and formal
                reply = f"As requested, here's a concise response: {text}."
            else:
                reply = f"[{p}] I heard: {text or '(image)'}"

    # Save assistant reply
    save_message(conv_id, "assistant", "assistant", reply, None)

    # Get conversation title
    conn = get_db_conn(); c = conn.cursor(); c.execute("SELECT title FROM conversations WHERE id=?", (conv_id,))
    row = c.fetchone(); conn.close()
    t = row["title"] if row else None

    return jsonify({"reply": reply, "image": image_url, "conv_id": conv_id, "title": t})

# history page
@app.route("/history")
def history_page():
    if "user" not in session: return redirect(url_for("login_route"))
    user = session["user"]; convs = list_conversations(user)
    html_parts = ["<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>History</title>",
                  "<style>body{background:#000;color:#fff;font-family:Inter;padding:20px} a{color:#0ff}</style></head><body>"]
    html_parts.append("<h2>Conversation History</h2><a href='/'>Back to Chat</a><div style='margin-top:12px'>")
    for conv in convs:
        html_parts.append(f"<div style='padding:12px;border:1px solid rgba(255,255,255,0.03);margin-top:8px;border-radius:8px'><h3>{conv['title'] or 'New chat'}</h3><small style='color:#9fb8c9'>Created: {conv['created']}</small>")
        conn = get_db_conn(); c = conn.cursor()
        c.execute("SELECT role, content, image, timestamp FROM messages WHERE conversation_id=? ORDER BY id", (conv["id"],))
        msgs = c.fetchall(); conn.close()
        html_parts.append("<div style='margin-top:8px'>")
        for m in msgs:
            html_parts.append(f"<div><b>{m['role'].capitalize()}:</b> {m['content']}</div>")
            if m['image']:
                html_parts.append(f"<div><img src='{m['image']}' style='max-width:220px;margin-top:6px;border-radius:6px'></div>")
            html_parts.append(f"<small style='color:#9fb8c9'>At: {m['timestamp']}</small><hr style='border-color:rgba(255,255,255,0.03)'>")
        html_parts.append("</div></div>")
    html_parts.append("</div></body></html>")
    return "".join(html_parts)

# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    print("🚀 Nexa UI running at http://127.0.0.1:5000")
    try: webbrowser.open("http://127.0.0.1:5000")
    except: pass
    app.run(host="0.0.0.0", port=5000, debug=True)


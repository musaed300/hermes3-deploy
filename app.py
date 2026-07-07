"""Hermes 3.0 Chat API"""
import os, json, sqlite3, ssl, urllib.request, urllib.error, random, string
from flask import Flask, request, jsonify, make_response

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
DEFAULT_MODEL = "moonshotai/kimi-k2.7-code"
DB_PATH = "/app/data/hermes.db"
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

app = Flask(__name__)

@app.after_request
def cors(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
    return response

@app.route("/<path:p>", methods=["OPTIONS"])
def opts(p): return make_response("", 204)

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = db()
    c.executescript('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT DEFAULT "New Chat", model TEXT DEFAULT "' + DEFAULT_MODEL + '", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, chat_id TEXT, role TEXT, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP); CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id);')
    c.commit(); c.close()

def gid(): return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

def msgs(cid):
    c = db()
    r = c.execute("SELECT role, content FROM messages WHERE chat_id=? ORDER BY created_at,id", (cid,)).fetchall()
    c.close()
    return [{"role":x["role"],"content":x["content"]} for x in r]

def save(cid, role, content):
    c = db()
    c.execute("INSERT INTO messages (chat_id,role,content) VALUES (?,?,?)", (cid,role,content))
    c.execute("UPDATE chats SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
    c.commit(); c.close()

def ai_call(messages, model):
    if not OPENROUTER_API_KEY: return None, "NO API KEY"
    payload = json.dumps({"model":model,"messages":messages,"temperature":0.7,"max_tokens":4000}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=payload, headers={"Authorization":"Bearer "+OPENROUTER_API_KEY,"Content-Type":"application/json","HTTP-Referer":"http://localhost:9119","X-Title":"Hermes"}, method="POST")
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=60) as r:
            d = json.loads(r.read().decode())
            ch = d.get("choices",[])
            return (ch[0]["message"]["content"], None) if ch else (None, "Empty")
    except urllib.error.HTTPError as e: return None, "HTTP "+str(e.code)
    except Exception as e: return None, str(e)

@app.route("/health")
def health(): return jsonify({"status":"ok","version":"3.0.3"})

@app.route("/chats", methods=["GET"])
def list_chats():
    c = db()
    rows = c.execute("SELECT * FROM chats ORDER BY updated_at DESC").fetchall()
    c.close()
    return jsonify({"chats":[dict(r) for r in rows]})

@app.route("/chats", methods=["POST"])
def create_chat():
    d = request.get_json(silent=True) or {}
    cid = gid()
    c = db()
    c.execute("INSERT INTO chats (id,title,model) VALUES (?,?,?)", (cid, d.get("title","New Chat"), d.get("model",DEFAULT_MODEL)))
    c.commit(); c.close()
    return jsonify({"id":cid,"title":d.get("title","New Chat"),"model":d.get("model",DEFAULT_MODEL)})

@app.route("/chats/<cid>", methods=["GET"])
def get_chat(cid):
    c = db()
    chat = c.execute("SELECT * FROM chats WHERE id=?", (cid,)).fetchone()
    if not chat: c.close(); return jsonify({"error":"Not found"}), 404
    m = c.execute("SELECT role,content,created_at FROM messages WHERE chat_id=? ORDER BY created_at,id", (cid,)).fetchall()
    c.close()
    return jsonify({"chat":dict(chat),"messages":[dict(x) for x in m]})

@app.route("/chats/<cid>", methods=["DELETE"])
def delete_chat(cid):
    c = db(); c.execute("DELETE FROM chats WHERE id=?", (cid,)); c.commit(); c.close()
    return jsonify({"deleted":cid})

@app.route("/chat", methods=["POST"])
def chat():
    d = request.get_json(silent=True) or {}
    cid = d.get("chat_id","")
    msg = d.get("message","").strip()
    model = d.get("model", DEFAULT_MODEL)
    if not msg: return jsonify({"error":"Empty"}), 400
    if not cid:
        cid = gid()
        c = db()
        c.execute("INSERT INTO chats (id,title,model) VALUES (?,?,?)", (cid, msg[:50], model))
        c.commit(); c.close()
    c = db()
    if not c.execute("SELECT id FROM chats WHERE id=?", (cid,)).fetchone(): c.close(); return jsonify({"error":"Not found"}), 404
    c.close()
    save(cid, "user", msg)
    history = msgs(cid)[-20:]
    reply, err = ai_call(history, model)
    if err: return jsonify({"error":err, "chat_id":cid}), 502
    save(cid, "assistant", reply)
    c = db()
    c.execute('UPDATE chats SET title=CASE WHEN title="New Chat" THEN ? ELSE title END, updated_at=CURRENT_TIMESTAMP WHERE id=?', (msg[:50], cid))
    c.commit(); c.close()
    return jsonify({"reply":reply, "chat_id":cid})

init()

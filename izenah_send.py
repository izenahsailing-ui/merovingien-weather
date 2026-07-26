# -*- coding: utf-8 -*-
"""IZENAH — envoi Telegram (bot). Stdlib uniquement (pas de dependance)."""
import urllib.request, urllib.parse, json, os, uuid, re, time
API = "https://api.telegram.org/bot%s/%s"

class SendError(Exception):
    """Echec d'envoi CONFIRME. Doit remonter : l'appelant ne doit jamais
    enregistrer un etat 'envoye' apres cette exception.

    ATTENTION : n'herite PAS de RuntimeError, volontairement. Le moniteur
    rattrape RuntimeError pour absorber les pannes de l'API meteo et sortir
    en succes ; si SendError en heritait, un echec d'envoi serait avale par
    ce meme filet et l'alerte disparaitrait sans bruit, ce que cette classe
    existe precisement pour empecher."""

def _post(token, method, fields, files=None, timeout=60, tries=3):
    """Envoie et VERIFIE. Telegram peut repondre HTTP 200 avec ok=false ;
    l'ancienne version renvoyait ce JSON sans le lire, et l'appelant marquait
    le message comme envoye. Un briefing ou une alerte pouvait donc etre perdu
    en silence. On retente, puis on leve une exception si ce n'est pas parti."""
    last = None
    for k in range(tries):
        try:
            res = _post_once(token, method, fields, files, timeout)
            if isinstance(res, dict) and res.get("ok"):
                return res
            last = (res or {}).get("description", "reponse sans ok=true")
        except Exception as ex:
            last = "%s: %s" % (type(ex).__name__, ex)
        if k < tries - 1:
            time.sleep(3 * (k + 1))
    raise SendError("%s a echoue apres %d tentatives : %s" % (method, tries, last))

def _post_once(token, method, fields, files=None, timeout=60):
    url = API % (token, method)
    if not files:
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(url, data=data)
    else:
        boundary = uuid.uuid4().hex
        body = b""
        for k, v in fields.items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode()
        for k, (fn, content, ctype) in files.items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n" % (boundary, k, fn, ctype)).encode()
            body += content + b"\r\n"
        body += ("--%s--\r\n" % boundary).encode()
        req = urllib.request.Request(url, data=body)
        req.add_header("Content-Type", "multipart/form-data; boundary=%s" % boundary)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

TG_MAX = 4000   # limite Telegram 4096, marge de securite

def send_message(token, chat_id, text):
    """Decoupe si necessaire : au-dela de 4096 caracteres Telegram refuse le
    message entier, ce qui faisait perdre le briefing quand un bulletin
    officiel etait long."""
    text = text or ""
    if len(text) <= TG_MAX:
        return _post(token, "sendMessage",
                     {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"})
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > TG_MAX:
            parts.append(cur); cur = line
        else:
            cur = (cur + "\n" + line) if cur else line
    if cur:
        parts.append(cur)
    res = None
    for i, p in enumerate(parts):
        suffix = "" if len(parts) == 1 else ("\n\n(%d/%d)" % (i + 1, len(parts)))
        res = _post(token, "sendMessage",
                    {"chat_id": chat_id, "text": p + suffix, "disable_web_page_preview": "true"})
    return res

def send_document(token, chat_id, path, caption=""):
    with open(path, "rb") as f:
        content = f.read()
    return _post(token, "sendDocument",
                 {"chat_id": str(chat_id), "caption": caption[:1000]},
                 {"document": (os.path.basename(path), content, "application/pdf")})

def get_updates(token):
    """Pour recuperer le chat_id : ecris un message au bot puis appelle ceci."""
    with urllib.request.urlopen(API % (token, "getUpdates"), timeout=20) as r:
        return json.loads(r.read().decode())

def _base(): return os.path.dirname(os.path.abspath(__file__))

def _extract(s):
    """Isole un token Telegram (123456:AAH...) dans un texte quelconque."""
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{30,}", s or "")
    return m.group(0) if m else ""

def load_token():
    """Token depuis izenah_config.json sinon depuis token.txt (rempli par l'utilisateur).
    Robuste : extrait la clé même si tout le message de BotFather est collé."""
    env = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if env:
        return _extract(env) or env
    c = os.path.join(_base(), "izenah_config.json")
    if os.path.exists(c):
        tok = _extract(str(json.load(open(c)).get("token", "")))
        if tok:
            return tok
    t = os.path.join(_base(), "token.txt")
    if os.path.exists(t):
        tok = _extract(open(t, encoding="utf-8").read())
        if tok:
            return tok
    return ""

def load_chat():
    env = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if env:
        return env
    c = os.path.join(_base(), "izenah_config.json")
    if os.path.exists(c):
        return str(json.load(open(c)).get("chat_id", "")).strip()
    return ""

def save_chat(chat_id):
    c = os.path.join(_base(), "izenah_config.json")
    cfg = json.load(open(c)) if os.path.exists(c) else {}
    cfg["chat_id"] = str(chat_id)
    json.dump(cfg, open(c, "w"), ensure_ascii=False, indent=2)

def detect_chat():
    tok = load_token()
    if not tok:
        return None
    res = get_updates(tok).get("result", [])
    cid = None
    for u in res:
        msg = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        ch = msg.get("chat", {})
        if ch.get("id"):
            cid = ch["id"]
    return cid

if __name__ == "__main__":
    import sys
    tok = load_token()
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "whoami":
        import urllib.request as _u
        print(_u.urlopen(API % (tok, "getMe"), timeout=15).read().decode())
    elif arg == "updates":
        print(json.dumps(get_updates(tok), indent=2, ensure_ascii=False))
    elif arg == "detectchat":
        cid = detect_chat()
        if cid:
            save_chat(cid); print("chat_id détecté et enregistré :", cid)
        else:
            print("Aucun chat détecté. Écris un message dans le groupe (bot présent) puis réessaie.")
    elif arg == "test":
        print(send_message(tok, load_chat(), "✅ Test IZENAH : le bot fonctionne."))
    else:
        print("Usage: whoami | updates | detectchat | test")

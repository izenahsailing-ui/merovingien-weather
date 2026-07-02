# -*- coding: utf-8 -*-
"""IZENAH — bilan mensuel d'auto-verification.
Compare les briefings archives (prevision de la veille pour le lendemain) aux
observations (reanalyse Open-Meteo) et envoie une note de performance sur Telegram.
Le systeme se note lui-meme : c'est ce qui permet de recaler les seuils au fil des saisons.
Lance le 1er du mois (workflow) ou a la main : python3 izenah_bilan.py [--nosend]
"""
import os, json, datetime, sys, urllib.request, urllib.parse
import izenah_send as T
from izenah_engine import PT_PRIMAIRE, col_vent, col_raf

BASE = os.path.dirname(os.path.abspath(__file__))
ARCH = os.path.join(BASE, "archives")

def observed(day_iso):
    """Vent max et rafale max OBSERVES (reanalyse) a La Ciotat, en noeuds."""
    q = dict(latitude=PT_PRIMAIRE[1], longitude=PT_PRIMAIRE[2],
             start_date=day_iso, end_date=day_iso, timezone="Europe/Paris",
             wind_speed_unit="kn", daily="wind_speed_10m_max,wind_gusts_10m_max")
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "izenah/1.0"}), timeout=25) as r:
        d = json.loads(r.read().decode()).get("daily", {})
    v = (d.get("wind_speed_10m_max") or [None])[0]
    g = (d.get("wind_gusts_10m_max") or [None])[0]
    return v, g

def feu_vent(v, g):
    cols = (col_vent(v or 0), col_raf(g or 0))
    return "R" if "R" in cols else ("A" if "A" in cols else "G")

def run(send=True):
    today = datetime.date.today()
    first = today.replace(day=1)
    last_month_end = first - datetime.timedelta(days=1)
    month_prefix = last_month_end.strftime("%Y-%m")
    rows = []
    for f in sorted(os.listdir(ARCH)):
        if not (f.startswith("brief_pour_%s" % month_prefix) and f.endswith(".json")):
            continue
        day = f[len("brief_pour_"):-len(".json")]
        try:
            b = json.load(open(os.path.join(ARCH, f)))
            ov, og = observed(day)
            if ov is None: continue
            rows.append(dict(day=day, pv=b.get("vent_max", 0), pg=b.get("raf_max", 0),
                             ov=ov, og=og or 0,
                             feu_p=b.get("nav", {}).get("color", "?"), feu_o=feu_vent(ov, og)))
        except Exception as e:
            print("skip", f, e)
    if not rows:
        print("Pas d'archive comparable pour", month_prefix)
        return None
    mae_v = sum(abs(r["pv"] - r["ov"]) for r in rows) / len(rows)
    mae_g = sum(abs(r["pg"] - r["og"]) for r in rows) / len(rows)
    hits = sum(1 for r in rows if r["feu_p"] == r["feu_o"])
    sur  = sum(1 for r in rows if "GAR".index(r["feu_p"] or "G") > "GAR".index(r["feu_o"]))
    sous = len(rows) - hits - sur
    msg = ("📊 BILAN MENSUEL · IZENAH (%s)\n"
           "%d briefings vérifiés contre la réalité :\n"
           "· Feu Navigation correct : %d/%d (%d%%) — %d trop prudent, %d trop optimiste\n"
           "· Écart moyen vent max : %.1f nœuds · rafales : %.1f nœuds\n"
           "Le système se recale avec ces chiffres au fil des saisons."
           % (month_prefix, len(rows), hits, len(rows), round(100 * hits / len(rows)),
              sur, sous, mae_v, mae_g))
    print(msg)
    if send:
        tok, chat = T.load_token(), T.load_chat()
        if tok and chat:
            T.send_message(tok, chat, msg)
            print(">> Bilan envoyé.")
    return msg

if __name__ == "__main__":
    run(send=("--nosend" not in sys.argv))

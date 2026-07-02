# -*- coding: utf-8 -*-
"""IZENAH — BMS Côte OFFICIEL Météo-France, sans clé API.
Le produit BMS marine a été retiré des portails de données (vérifié 2 juil. 2026),
mais meteofrance.com le sert via son flux interne rwg.meteofrance.com avec le
jeton PUBLIC embarqué dans le site. On appelle ce flux directement.

Zone : BMSCOTE-02 (Méditerranée), sous-zone BMSCOTE-02-02 (Port-Camargue /
Saint-Raphaël) = PROVENCE « de Beauduc à Cap Croisette » et voisines -> La Ciotat.
Dégradation gracieuse : erreur ou 404 (« pas de BMS en cours ») -> None / inactif.
"""
import json, urllib.request, datetime, os, time

os.environ.setdefault("TZ", "Europe/Paris")
try: time.tzset()
except Exception: pass

# Jeton public du site meteofrance.com (le même pour tous les visiteurs).
TOKEN = "__Wj7dVSTjV9YGu1guveLyDq0g7S7TfTjaHBTPTpO0kj8__"
DOMAIN = "BMSCOTE-02"
ZONE = "BMSCOTE-02-02"
URL = ("https://rwg.meteofrance.com/internet2018client/2.0/report"
       "?domain=%s&report_type=marine&report_subtype=BMS_cote_fr&format=&token=%s")

def _paris(ts):
    try:
        if isinstance(ts, (int, float)):
            return datetime.datetime.fromtimestamp(ts)
        return (datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                .astimezone().replace(tzinfo=None))
    except Exception:
        return None

def _fr(dt):
    if not dt: return ""
    J=["lun","mar","mer","jeu","ven","sam","dim"]
    return "%s %d à %dh%02d" % (J[dt.weekday()], dt.day, dt.hour, dt.minute)

def fetch_bms():
    """None si pas de BMS en cours. Sinon dict:
    avis, numero, actif_zone (True = concerne NOTRE côte), zone_titre, zone_texte,
    debut, fin (heure de Paris, lisible), maj, sig (anti-spam)."""
    try:
        req = urllib.request.Request(URL % (DOMAIN, TOKEN),
                                     headers={"User-Agent": "Mozilla/5.0 (izenah)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return None if e.code == 404 else None
    except Exception:
        return None
    blocs = data.get("text_bloc_item") or []
    avis = numero = ""
    for b in blocs:
        if not b.get("bloc_title"):
            for t in b.get("text_items", []):
                s = (t.get("title") or t.get("text") or "").strip()
                if s.lower().startswith("avis"): avis = s.rstrip(".")
                if s.lower().startswith("bms") and ("numéro" in s.lower() or "numero" in s.lower()): numero = s
    zone_blocs = [b for b in blocs if b.get("bloc_title") and ZONE in (b.get("domain_id") or [])]
    zt = zx = ""
    deb = fin = None
    if zone_blocs:
        b = zone_blocs[0]
        zt = b.get("bloc_title", "")
        zx = " ".join((t.get("text") or t.get("title") or "").strip()
                      for t in b.get("text_items", [])).strip()
        deb = _paris(b.get("begin_time")); fin = _paris(b.get("end_time"))
    if fin is None: fin = _paris(data.get("end_validity_time"))
    grave = any(w in avis.lower() for w in ("coup de vent", "tempête", "tempete", "ouragan", "violente"))
    return dict(avis=avis or "BMS en cours", numero=numero,
                actif_zone=bool(zone_blocs), zone_titre=zt, zone_texte=zx,
                debut=_fr(deb), fin=_fr(fin), maj=_fr(_paris(data.get("update_time"))),
                debut_iso=(deb.isoformat() if deb else None),
                fin_iso=(fin.isoformat() if fin else None),
                grave=grave,
                sig="%s|%s|%s" % (numero, avis, bool(zone_blocs)))

if __name__ == "__main__":
    b = fetch_bms()
    print(json.dumps(b, ensure_ascii=False, indent=1) if b else "Pas de BMS Côte Méditerranée en cours.")

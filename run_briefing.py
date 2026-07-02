# -*- coding: utf-8 -*-
"""IZENAH — orchestrateur du briefing du soir.
build_brief -> rendu PDF -> archive (datee du JOUR CIBLE) -> envoi Telegram.

Gardes de fiabilite (les crons GitHub sont retardes/sautes sans prevenir) :
- anti-doublon : si le briefing du jour cible est deja parti, on ne renvoie pas
  (permet des crons redondants : le premier qui passe envoie, les autres se taisent) ;
- anti-minuit : un cron retarde apres minuit calculerait pour le surlendemain -> refus ;
- fenetre horaire : en 'schedule', n'envoie qu'entre 18h00 et 23h59 heure de Paris
  (gere aussi ete/hiver : les crons UTC couvrent les deux, la decision est locale).
Un declenchement manuel (workflow_dispatch / ligne de commande) passe outre la fenetre.

Usage: python3 run_briefing.py [--nosend] [--force]
"""
import os, json, datetime, sys, shutil
from izenah_engine import build_brief
from izenah_render import render, synthese_telegram
import izenah_send

BASE = os.path.dirname(os.path.abspath(__file__))
ARCH = os.path.join(BASE, "archives")
SENT = os.path.join(BASE, "sent_state.json")

def _sent_state():
    try: return json.load(open(SENT))
    except Exception: return {}

def mark_sent(target_iso):
    st = _sent_state(); st["briefing_target"] = target_iso
    st["at"] = datetime.datetime.now().isoformat()
    json.dump(st, open(SENT, "w"))

def already_sent(target_iso):
    return _sent_state().get("briefing_target") == target_iso

def main(send=True, force=False):
    os.makedirs(ARCH, exist_ok=True)
    now = datetime.datetime.now()
    target = (now.date() + datetime.timedelta(days=1)).isoformat()
    scheduled = os.environ.get("GITHUB_EVENT_NAME", "") == "schedule"

    if already_sent(target) and not force:
        print(">> Briefing pour %s deja envoye, rien a faire (garde anti-doublon)." % target)
        return None
    if scheduled and not force and not (18 <= now.hour <= 23):
        print(">> Cron hors fenetre (il est %dh%02d Paris) : on attend le bon creneau." % (now.hour, now.minute))
        return None

    b = build_brief()
    pdf = os.path.join(ARCH, "briefing_pour_%s.pdf" % target)
    render(b, pdf)
    with open(os.path.join(ARCH, "brief_pour_%s.json" % target), "w") as f:
        json.dump(b, f, ensure_ascii=False, default=str)
    try: shutil.copy(pdf, os.path.join(BASE, "Briefing_Izenah.pdf"))
    except Exception: pass
    txt = synthese_telegram(b)
    print(txt)
    tok, chat = izenah_send.load_token(), izenah_send.load_chat()
    if send and tok and chat:
        izenah_send.send_message(tok, chat, txt)
        izenah_send.send_document(tok, chat, pdf, caption="Briefing détaillé pour le %s" % target)
        mark_sent(target)
        print(">> Envoyé sur Telegram (%s)" % chat)
    elif send:
        print(">> Token ou chat_id manquant : envoi sauté (token.txt rempli ? groupe créé ?).")
    else:
        mark_sent(target)
        print(">> Envoi désactivé (--nosend).")
    return pdf

if __name__ == "__main__":
    main(send=("--nosend" not in sys.argv), force=("--force" in sys.argv))

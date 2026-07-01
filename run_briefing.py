# -*- coding: utf-8 -*-
"""IZENAH — orchestrateur du briefing du soir.
build_brief -> rendu PDF -> archive -> envoi Telegram (si config presente).
Usage: python3 run_briefing.py [--nosend]
"""
import os, json, datetime, sys, shutil
from izenah_engine import build_brief
from izenah_render import render, synthese_telegram
import izenah_send

BASE = os.path.dirname(os.path.abspath(__file__))
ARCH = os.path.join(BASE, "archives")
CFG  = os.path.join(BASE, "izenah_config.json")

def main(send=True):
    os.makedirs(ARCH, exist_ok=True)
    b = build_brief()
    today = datetime.date.today().isoformat()
    pdf = os.path.join(ARCH, "briefing_%s.pdf" % today)
    render(b, pdf)
    # archive donnees brutes (analyses inter-saisons)
    with open(os.path.join(ARCH, "brief_%s.json" % today), "w") as f:
        json.dump(b, f, ensure_ascii=False, default=str)
    # copie "dernier briefing" a la racine du projet
    try: shutil.copy(pdf, os.path.join(BASE, "Briefing_Izenah.pdf"))
    except Exception: pass
    txt = synthese_telegram(b)
    print(txt)
    tok, chat = izenah_send.load_token(), izenah_send.load_chat()
    if send and tok and chat:
        izenah_send.send_message(tok, chat, txt)
        izenah_send.send_document(tok, chat, pdf, caption="Briefing détaillé du %s" % today)
        print(">> Envoyé sur Telegram (%s)" % chat)
    elif send:
        print(">> Token ou chat_id manquant : envoi sauté (token.txt rempli ? groupe créé ?).")
    else:
        print(">> Envoi désactivé (--nosend).")
    return pdf

if __name__ == "__main__":
    main(send=("--nosend" not in sys.argv))

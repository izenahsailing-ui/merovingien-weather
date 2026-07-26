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
    """Ecriture atomique : un run interrompu ne laisse plus un JSON tronque."""
    st = _sent_state(); st["briefing_target"] = target_iso
    st["at"] = datetime.datetime.now().isoformat()
    tmp = SENT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, SENT)

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
    # GARDE ANTI-MINUIT, desormais valable sur TOUS les chemins et pas seulement
    # sur les crons : le declencheur principal est un workflow_dispatch, donc
    # l'ancienne garde ne s'appliquait jamais au chemin nominal. Un lancement
    # apres minuit calculait le briefing du SURLENDEMAIN, l'envoyait, et
    # marquait ce jour comme traite : le vrai briefing du soir sautait.
    if now.hour < 12 and not force:
        print(">> Il est %dh%02d Paris : trop tot pour un briefing du soir, on refuse "
              "(utiliser --force pour passer outre)." % (now.hour, now.minute))
        return None
    # fenetre d'envoi : APRES la maj Meteo-France de 18h15 (cible 18h30), jusqu'a minuit
    if scheduled and not force and not (now.hour > 18 or (now.hour == 18 and now.minute >= 25)) :
        print(">> Cron hors fenetre (il est %dh%02d Paris) : on attend 18h25+." % (now.hour, now.minute))
        return None

    b = build_brief()
    with open(os.path.join(ARCH, "brief_pour_%s.json" % target), "w") as f:
        json.dump(b, f, ensure_ascii=False, default=str)
    txt = synthese_telegram(b)
    print(txt)

    tok, chat = izenah_send.load_token(), izenah_send.load_chat()
    if send and not (tok and chat):
        # Avant : print + sortie en SUCCES. Un secret expire rendait donc le
        # systeme muet pendant des semaines sans declencher la moindre alerte.
        raise SystemExit(">> ECHEC : token ou chat_id Telegram absent, rien n'a ete envoye.")

    if send:
        # Le TEXTE d'abord : c'est la synthese de securite. Le PDF, plus fragile
        # a fabriquer, ne doit jamais pouvoir l'empecher de partir.
        izenah_send.send_message(tok, chat, txt)
        mark_sent(target)
        print(">> Synthese envoyee sur Telegram (%s)" % chat)
    else:
        print(">> Envoi desactive (--nosend) : l'etat n'est PAS marque envoye.")

    pdf = os.path.join(ARCH, "briefing_pour_%s.pdf" % target)
    try:
        render(b, pdf)
        try: shutil.copy(pdf, os.path.join(BASE, "Briefing_Izenah.pdf"))
        except Exception: pass
        if send:
            izenah_send.send_document(tok, chat, pdf, caption="Briefing détaillé pour le %s" % target)
            print(">> Document envoye.")
    except Exception as ex:
        print(">> Document non envoye (%s: %s). La synthese, elle, est partie." % (type(ex).__name__, ex))
        if send:
            try:
                izenah_send.send_message(tok, chat,
                    "⚠️ Le document détaillé n'a pas pu être produit ce soir. "
                    "La synthèse ci-dessus reste valable.")
            except Exception:
                pass
    return pdf

if __name__ == "__main__":
    main(send=("--nosend" not in sys.argv), force=("--force" in sys.argv))

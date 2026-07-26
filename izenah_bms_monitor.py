# -*- coding: utf-8 -*-
"""IZENAH — moniteur 'coup de vent' (équivalent BMS), sans clé API.
Surveille les 48 prochaines heures sur La Ciotat + Cap Sicié et alerte sur
Telegram DÈS qu'un épisode venteux dangereux apparaît dans les prévisions
(avec son horaire). Anti-spam via bms_state.json. À lancer chaque heure."""
import datetime, json, os, sys, re
import izenah_engine as E
import izenah_send as T

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "bms_state.json")
HEALTH = os.path.join(BASE, "health_state.json")
HORIZON_H = 48

def _notify(send, msg):
    """Envoie et renvoie True SEULEMENT si c'est parti et confirme.
    Regle absolue : on n'ecrit jamais l'etat anti-repetition avant ce True,
    sinon une alerte non partie est comptee comme traitee et perdue pour de bon."""
    if not send:
        return True                      # mode --nosend : on n'ecrit pas d'etat non plus
    tok, chat = T.load_token(), T.load_chat()
    if not tok or not chat:
        raise RuntimeError("secret Telegram absent : impossible d'alerter")
    T.send_message(tok, chat, msg)       # leve SendError si l'envoi echoue
    return True

def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(path, obj):
    """Ecriture atomique : un run interrompu ne laisse plus un JSON tronque
    qui fait planter tous les passages suivants."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)

def watchdog_briefing(send=True):
    """Filet de securite : si le briefing du soir n'est pas parti a 19h passees
    (cron GitHub retarde/saute), on l'envoie d'ici. Ne fait rien sinon."""
    now = datetime.datetime.now()
    if not (19 <= now.hour <= 23):
        return
    try:
        import run_briefing
        target = (now.date() + datetime.timedelta(days=1)).isoformat()
        if run_briefing.already_sent(target):
            return
        print(">> WATCHDOG : briefing du soir manquant, envoi de rattrapage.")
        run_briefing.main(send=send, force=True)
    except Exception as e:
        print(">> Watchdog briefing en echec:", e)

def weekly_health(send=True):
    """Le dimanche soir : un court bilan pour prouver que le systeme vit."""
    now = datetime.datetime.now()
    if not (now.weekday() == 6 and 18 <= now.hour <= 22):
        return
    wk = now.strftime("%G-W%V")
    try: st = json.load(open(HEALTH))
    except Exception: st = {}
    if st.get("week") == wk:
        return
    # Comptage par la DATE DU NOM DE FICHIER : git ne conserve pas les dates de
    # modification, donc l'ancien comptage par mtime renvoyait le total depuis
    # toujours apres chaque checkout.
    arch = os.path.join(BASE, "archives")
    cnt = 0
    try:
        for f in os.listdir(arch):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
            if f.startswith("briefing") and f.endswith(".pdf") and m:
                d = datetime.date.fromisoformat(m.group(1))
                if 0 <= (now.date() - d).days <= 7:
                    cnt += 1
    except Exception:
        pass
    msg = ("🟢 SANTÉ DU SYSTÈME · IZENAH\n"
           "Semaine écoulée : %d briefing(s) envoyé(s), surveillance vent active.\n"
           "Prochain briefing : demain 18h30." % cnt)
    if _notify(send, msg):
        _save(HEALTH, {"week": wk, "at": now.isoformat()})

def run(send=True):
    now = datetime.datetime.now()
    watchdog_briefing(send=send)
    weekly_health(send=send)
    # --- Vigilance officielle Meteo-France (prioritaire, si cle MF_APIKEY presente) ---
    try:
        import izenah_vigilance
        vig = izenah_vigilance.fetch_vigilance()
    except Exception:
        vig = None
    if vig and vig.get("max_color", 1) >= 3:
        vsig = "VIG|%s|%s" % (now.date(), vig["max_label"])
        vstate = os.path.join(BASE, "vig_state.json")
        prev = _load(vstate)
        if prev.get("sig") != vsig:
            ph = ", ".join("%s %s" % (k, v) for k, v in vig.get("phenos", {}).items())
            vmsg = ("🟧 VIGILANCE OFFICIELLE · IZENAH\n"
                    "Météo-France : vigilance %s sur ta zone (Var / Bouches-du-Rhône).\n%s\n\n"
                    "⚓ Prudence maximale. Détails : https://vigilance.meteofrance.fr/fr" % (vig["max_label"].upper(), ph))
            if _notify(send, vmsg):
                _save(vstate, {"sig": vsig, "at": now.isoformat()})
    # --- BMS COTE OFFICIEL Meteo-France (sans cle, prioritaire sur l'estimation) ---
    try:
        import izenah_bms_officiel
        bo = izenah_bms_officiel.fetch_bms()
    except Exception:
        bo = None
    if bo and bo.get("actif_zone"):
        bstate_p = os.path.join(BASE, "bmsoff_state.json")
        prev = _load(bstate_p)
        if prev.get("sig") != bo["sig"]:
            bmsg = ("🟥 BMS CÔTE OFFICIEL · IZENAH\n"
                    "Météo-France émet : %s\n"
                    "%s\n%s\n"
                    "Valable jusqu'à %s.\n\n"
                    "⚓ Anticipe : La Ciotat par Mistral, La Madrague par vent d'Est, port si les deux sont exposés.\n"
                    "🔗 https://meteofrance.com/meteo-marine/marseille-la-ciotat/MICROZONE-30"
                    % (bo["avis"], bo.get("zone_titre",""), bo.get("zone_texte",""), bo.get("fin","")))
            if _notify(send, bmsg):
                _save(bstate_p, {"sig": bo["sig"], "at": now.isoformat()})

    # --- Surveillance modele (coup de vent imminent) ---
    fc = E.om_forecast(*E.PT_PRIMAIRE[1:], days=3)
    cap = E.om_forecast(*E.PT_CAP_SICIE[1:], days=3)
    H = fc["hourly"]; times = [datetime.datetime.fromisoformat(t) for t in H["time"]]; n = len(times)
    win = [i for i in range(n) if 0 <= (times[i] - now).total_seconds() <= HORIZON_H * 3600]
    if not win:
        return None
    peak_s = peak_g = 0; start_i = None
    for i in win:
        _, gmx, _ = E.cross_stats(H, "wind_gusts_10m", i)
        _, _, smn = E.cross_stats(H, "wind_speed_10m", i)
        g = gmx or 0; s = smn or 0
        peak_g = max(peak_g, g); peak_s = max(peak_s, s)
        if start_i is None and (g >= 34 or s >= 28):
            start_i = i
    # Cap Sicié (AROME) sur 48 h
    capH = cap["hourly"]; ct = [datetime.datetime.fromisoformat(t) for t in capH["time"]]
    cg = capH.get("wind_gusts_10m_meteofrance_arome_france_hd", [])
    cidx = [i for i in range(len(ct)) if 0 <= (ct[i] - now).total_seconds() <= HORIZON_H * 3600]
    cs = max((cg[i] for i in cidx if i < len(cg) and cg[i] is not None), default=0)
    peak_g = max(peak_g, cs)
    # probabilité d'ensemble (rafales > 34 kn sur 48 h)
    ens = E.om_ensemble(*E.PT_PRIMAIRE[1:], days=3)
    EH = ens["hourly"]; et = [datetime.datetime.fromisoformat(t) for t in EH["time"]]
    ei = [i for i in range(len(et)) if 0 <= (et[i] - now).total_seconds() <= HORIZON_H * 3600]
    keys = [k for k in EH.keys() if k.startswith("wind_gusts_10m")]
    tot = cnt = 0
    for mk in keys:
        s = EH[mk]; mx = max((s[i] for i in ei if i < len(s) and s[i] is not None), default=None)
        if mx is None: continue
        tot += 1; cnt += (1 if mx > 34 else 0)
    p34 = round(100 * cnt / tot) if tot else 0

    if peak_s >= 28 or peak_g >= 40:
        level, head = "ROUGE", "🔴 COUP DE VENT"
    elif peak_s >= 22 or peak_g >= 34:
        level, head = "ORANGE", "🟠 RENFORCEMENT NOTABLE"
    else:
        # plus d'episode en vue : si on avait annonce un episode A VENIR, on previent qu'il est annule
        state = _load(STATE)
        sig_prev = state.get("last_sig", "")
        if sig_prev and not state.get("lifted"):
            try: ep_date = datetime.date.fromisoformat(sig_prev.split("|")[0])
            except Exception: ep_date = None
            if ep_date and ep_date >= now.date():
                msg = ("🟢 LEVÉE D'ALERTE · IZENAH\n"
                       "L'épisode venteux annoncé (%s) a disparu des dernières prévisions.\n"
                       "Retour à une situation normale." % E.fr_jour(ep_date))
                if _notify(send, msg):
                    state["lifted"] = True; state["at"] = now.isoformat()
                    _save(STATE, state)
                return msg
        return None

    if start_i is not None:
        st = times[start_i]
        jour = ("aujourd'hui" if st.date() == now.date()
                else ("demain" if st.date() == (now + datetime.timedelta(days=1)).date() else E.fr_jour(st.date())))
        quand = "%s à partir de %s" % (jour, st.strftime("%Hh"))
        sig = "%s|%s" % (st.date(), level)
    else:
        quand = "dans les 48 h"
        sig = "%s|%s" % (now.date(), level)

    state = _load(STATE)
    if state.get("last_sig") == sig and not state.get("lifted"):
        return None  # déjà alerté pour cet épisode/niveau (et pas levé entre-temps)

    msg = ("⚠️ ALERTE VENT · IZENAH (%s)\n"
           "Épisode venteux prévu sur La Ciotat ↔ Les Embiez : %s.\n\n"
           "Vent moyen jusqu'à %d kn, rafales %d kn (Cap Sicié %d kn).\n"
           "Probabilité de rafales > 34 kn (48 h) : %d %%.\n\n"
           "⚓ Anticipe un mouillage très protégé : La Ciotat par Mistral, La Madrague par vent d'Est.\n"
           "ℹ️ Bulletin officiel (BMS) Météo-France : https://meteofrance.com/meteo-marine/la-ciotat/570199"
           % (head, quand, round(peak_s), round(peak_g), round(cs), p34))

    if _notify(send, msg):
        _save(STATE, {"last_sig": sig, "at": now.isoformat()})
    return msg

if __name__ == "__main__":
    try:
        m = run(send=("--nosend" not in sys.argv))
        print(m if m else "RAS : aucun épisode venteux notable dans les 48 h.")
    except RuntimeError as e:
        # panne/rate-limit API meteo : pas un bug -> on sort proprement,
        # le passage suivant (30 min) reessaiera. Aucune alerte d'echec envoyee.
        print(">> API meteo indisponible sur ce passage (%s). Reessai au prochain run." % e)
    except Exception as e:
        import traceback; traceback.print_exc()
        raise

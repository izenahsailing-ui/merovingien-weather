# -*- coding: utf-8 -*-
"""IZENAH — moniteur 'coup de vent' (équivalent BMS), sans clé API.
Surveille les 48 prochaines heures sur La Ciotat + Cap Sicié et alerte sur
Telegram DÈS qu'un épisode venteux dangereux apparaît dans les prévisions
(avec son horaire). Anti-spam via bms_state.json. À lancer chaque heure."""
import datetime, json, os, sys
import izenah_engine as E
import izenah_send as T

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "bms_state.json")
HORIZON_H = 48

def run(send=True):
    now = datetime.datetime.now()
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

    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if state.get("last_sig") == sig:
        return None  # déjà alerté pour cet épisode/niveau

    msg = ("⚠️ ALERTE VENT · IZENAH (%s)\n"
           "Épisode venteux prévu sur La Ciotat ↔ Les Embiez : %s.\n\n"
           "Vent moyen jusqu'à %d kn, rafales %d kn (Cap Sicié %d kn).\n"
           "Probabilité de rafales > 34 kn (48 h) : %d %%.\n\n"
           "⚓ Anticipe un mouillage très protégé : La Ciotat par Mistral, La Madrague par vent d'Est.\n"
           "ℹ️ Bulletin officiel (BMS) Météo-France : https://meteofrance.com/meteo-marine/la-ciotat/570199"
           % (head, quand, round(peak_s), round(peak_g), round(cs), p34))

    if send:
        tok, chat = T.load_token(), T.load_chat()
        if tok and chat:
            T.send_message(tok, chat, msg)
    json.dump({"last_sig": sig, "at": now.isoformat()}, open(STATE, "w"))
    return msg

if __name__ == "__main__":
    m = run(send=("--nosend" not in sys.argv))
    print(m if m else "RAS : aucun épisode venteux notable dans les 48 h.")

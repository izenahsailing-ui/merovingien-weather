# -*- coding: utf-8 -*-
"""Erreur REELLE de chaque modele, mesuree contre l'observation du Bec de
l'Aigle sur 18 mois. Remplace les poids poses au juge par des poids mesures."""
import json, math, statistics as S

MODELS = ["meteofrance_arome_france_hd", "meteofrance_arpege_europe",
          "ecmwf_ifs025", "icon_eu", "icon_global", "gfs_seamless"]
COURT = {"meteofrance_arome_france_hd": "AROME 1,5 km", "meteofrance_arpege_europe": "ARPEGE 11 km",
         "ecmwf_ifs025": "ECMWF 25 km", "icon_eu": "ICON-EU 7 km",
         "icon_global": "ICON glob 11 km", "gfs_seamless": "GFS 13 km"}
SECT = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

obs = {}
for t, ff, dd, fxi in json.load(open("obs_bec.json")):
    # AAAAMMJJHH -> ISO
    iso = "%s-%s-%sT%s:00" % (t[0:4], t[4:6], t[6:8], t[8:10])
    obs[iso] = (ff, dd, fxi)

prev = json.load(open("prev_bec.json"))
times = prev["time"]

def sect(d):
    if d is None: return None
    return SECT[int((d % 360) / 45 + 0.5) % 8]

def stats(errs):
    if len(errs) < 30: return None
    m = sum(errs) / len(errs)
    mae = sum(abs(e) for e in errs) / len(errs)
    rmse = math.sqrt(sum(e * e for e in errs) / len(errs))
    return m, mae, rmse, len(errs)

print("=" * 78)
print("ERREUR MESUREE SUR 18 MOIS · Bec de l'Aigle · %d heures" % len(times))
print("=" * 78)

res = {}
for var, obs_i, lab in (("wind_speed_10m", 0, "VENT MOYEN"), ("wind_gusts_10m", 2, "RAFALES")):
    print("\n%s  (m/s ; biais positif = le modele surestime)" % lab)
    print("  %-18s %8s %8s %8s %7s" % ("modele", "biais", "MAE", "RMSE", "n"))
    for mid in MODELS:
        s = prev.get("%s_%s" % (var, mid))
        if not s: continue
        errs = []
        for k, t in enumerate(times):
            o = obs.get(t)
            if not o or o[obs_i] is None or k >= len(s) or s[k] is None: continue
            errs.append(s[k] - o[obs_i])
        st = stats(errs)
        if not st: continue
        res.setdefault(var, {})[mid] = st
        print("  %-18s %+8.2f %8.2f %8.2f %7d" % (COURT[mid], st[0], st[1], st[2], st[3]))

# --- biais par secteur de vent observe (le vrai effet de site) ---
print("\nBIAIS DU VENT MOYEN PAR SECTEUR OBSERVE (m/s)")
hdr = "  %-18s" % "modele" + "".join("%7s" % x for x in SECT)
print(hdr)
biais_sect = {}
for mid in MODELS:
    s = prev.get("wind_speed_10m_%s" % mid)
    if not s: continue
    per = {x: [] for x in SECT}
    for k, t in enumerate(times):
        o = obs.get(t)
        if not o or o[0] is None or o[1] is None or k >= len(s) or s[k] is None: continue
        se = sect(o[1])
        if se: per[se].append(s[k] - o[0])
    line = "  %-18s" % COURT[mid]
    biais_sect[mid] = {}
    for x in SECT:
        if len(per[x]) >= 40:
            b = sum(per[x]) / len(per[x]); biais_sect[mid][x] = b
            line += "%+7.2f" % b
        else:
            line += "%7s" % "."
    print(line)

# --- poids mesures : inverse de l'erreur quadratique, normalises ---
print("\nPOIDS MESURES (inverse du RMSE, normalises a 1 pour le meilleur)")
for var, lab in (("wind_speed_10m", "vent"), ("wind_gusts_10m", "rafales")):
    if var not in res: continue
    inv = {m: 1.0 / st[2] for m, st in res[var].items()}
    best = max(inv.values())
    print("  %s :" % lab, ", ".join("%s %.2f" % (COURT[m], inv[m] / best)
                                    for m in sorted(inv, key=lambda x: -inv[x])))

# --- rapport rafale/vent observe, pour caler le garde-fou ---
rr = [o[2] / o[0] for o in obs.values() if o[0] and o[2] and o[0] > 3]
rr.sort()
print("\nRAPPORT RAFALE / VENT OBSERVE (vent > 3 m/s, n=%d)" % len(rr))
print("  p01 %.2f  p05 %.2f  median %.2f  p95 %.2f  p99 %.2f  max %.2f"
      % (rr[int(.01 * len(rr))], rr[int(.05 * len(rr))], rr[len(rr) // 2],
         rr[int(.95 * len(rr))], rr[int(.99 * len(rr))], rr[-1]))

json.dump({"biais_sect": biais_sect,
           "rmse": {v: {m: st[2] for m, st in d.items()} for v, d in res.items()},
           "biais": {v: {m: st[0] for m, st in d.items()} for v, d in res.items()},
           "ratio_obs": {"p01": rr[int(.01 * len(rr))], "p99": rr[int(.99 * len(rr))],
                         "median": rr[len(rr) // 2]}},
          open("calibration.json", "w"), indent=1)
print("\n-> calibration.json ecrit")

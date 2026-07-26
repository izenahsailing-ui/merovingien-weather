# -*- coding: utf-8 -*-
"""IZENAH - couche modeles v8.

Corrige les 7 defauts d'interpretation trouves dans izenah_engine.py :
  1. ECMWF ifs025 ne fournit PAS de rafales -> declare, jamais compte en douce
  2. Rafale lointaine ne vient plus d'un modele global isole -> ensembles
  3. AROME s'arrete a 48 h -> l'estimateur ne change plus de nature en silence
  4. Modeles correles (AROME emboite dans ARPEGE) -> poids par CENTRE
  5. ECMWF est 3-horaire interpole -> marque, poids reduit sur l'heure fine
  6. Runs d'ages differents -> age declare
  7. "p75 pondere" qui n'en etait pas -> vrais quantiles ponderes
"""
import urllib.request, urllib.parse, json, time, datetime, math

LAT, LON = 43.175, 5.607
TZ = "Europe/Paris"

# ---- Registre des sources. Verifie sur la doc Open-Meteo le 26/07/2026. ----
# gust=False : le modele ne fournit PAS wind_gusts_10m.
SOURCES = [
    # id                          centre    maille_km  portee_h  dt_h  gust
    ("meteofrance_arome_france_hd", "MF",      1.5,       48,     1,   True),
    ("meteofrance_arpege_europe",   "MF",     11.0,       96,     1,   True),
    # VERIFIE EN DIRECT le 26/07/2026 : contrairement a la doc, ifs025 renvoie
    # bien des rafales, et leur dispersion (ecart-type du rapport rafale/vent
    # = 0,21) prouve un vrai diagnostic, pas une formule appliquee au vent.
    ("ecmwf_ifs025",                "ECMWF",  25.0,      360,     3,   True),
    ("icon_eu",                     "DWD",     7.0,      120,     1,   True),
    ("icon_global",                 "DWD",    11.0,      180,     1,   True),
    ("gfs_seamless",                "NCEP",   13.0,      384,     1,   True),
]
# Identifiants d'ensemble verifies en direct. 4 centres independants, 140 membres.
ENSEMBLES = [
    ("ecmwf_ifs025",             "ECMWF"),   # 51 membres
    ("icon_eu_eps",              "DWD"),     # 40 membres
    ("gfs025",                   "NCEP"),    # 31 membres
    ("ukmo_global_ensemble_20km","UKMO"),    # 18 membres
]

# Garde-fou physique sur les rafales. Mesure sur ce point : GFS produit des
# rapports rafale/vent de 0,46 a 4,37, physiquement impossibles sur mer
# (une rafale ne peut pas etre plus faible que le vent moyen, ni 4 fois plus
# forte). Les autres modeles restent entre 0,9 et 2,4. On rejette la valeur
# au lieu de la laisser piloter une alerte.
GUST_RATIO_MIN, GUST_RATIO_MAX = 1.05, 2.60

# Poids nominaux par CENTRE et par echeance (jours). Un centre = une voix,
# repartie entre ses modeles. Evite qu'AROME + ARPEGE pesent double.
def centre_weight(centre, lead_h):
    d = lead_h / 24.0
    if centre == "MF":    return 3.0 if d <= 2 else (1.6 if d <= 4 else 0.0)
    if centre == "ECMWF": return 1.6 if d <= 2 else 2.2
    if centre == "DWD":   return 1.4 if d <= 2 else 1.6
    if centre == "NCEP":  return 1.0
    return 1.0

# Penalite de maille : un modele qui ne voit pas la baie vaut moins a courte echeance
def mesh_factor(km, lead_h):
    if lead_h > 48: return 1.0
    return min(1.0, (8.0 / km) ** 0.35)

def fetch(url, tries=4, timeout=25):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "izenah/8.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as ex:
            last = ex; time.sleep(1.5 * (k + 1))
    raise RuntimeError("fetch: %s" % last)

def get_forecast(days=8):
    q = dict(latitude=LAT, longitude=LON, timezone=TZ, wind_speed_unit="kn",
             forecast_days=days, cell_selection="sea",
             models=",".join(s[0] for s in SOURCES),
             hourly="wind_speed_10m,wind_gusts_10m,wind_direction_10m")
    return fetch("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q))

def get_ensembles(days=10):
    out = {}
    for mid, centre in ENSEMBLES:
        try:
            q = dict(latitude=LAT, longitude=LON, timezone=TZ, wind_speed_unit="kn",
                     forecast_days=days, models=mid,
                     hourly="wind_speed_10m,wind_gusts_10m")
            out[mid] = (centre, fetch("https://ensemble-api.open-meteo.com/v1/ensemble?"
                                      + urllib.parse.urlencode(q)))
        except Exception as ex:
            out[mid] = (centre, None)
    return out

# ---------------- Quantiles ponderes (vrais, pas un p75 bricole) ----------------
def wquantile(pairs, p):
    """pairs = [(valeur, poids)]. Quantile p par interpolation sur les poids cumules."""
    pairs = sorted((v, w) for v, w in pairs if v is not None and w > 0)
    if not pairs: return None
    if len(pairs) == 1: return pairs[0][0]
    tot = sum(w for _, w in pairs)
    acc, prev_v, prev_c = 0.0, pairs[0][0], 0.0
    for v, w in pairs:
        c0 = acc / tot
        acc += w
        c1 = acc / tot
        cm = (c0 + c1) / 2.0
        if cm >= p:
            if cm == prev_c: return v
            t = (p - prev_c) / (cm - prev_c) if cm > prev_c else 1.0
            return prev_v + t * (v - prev_v)
        prev_v, prev_c = v, cm
    return pairs[-1][0]

def series(H, var, mid):
    return H.get("%s_%s" % (var, mid))

class Point:
    """Etat d'une variable a une heure : distribution ponderee + tracabilite."""
    __slots__ = ("q10", "q50", "q90", "n", "centres", "sources", "note")
    def __init__(s, q10, q50, q90, n, centres, sources, note):
        s.q10, s.q50, s.q90 = q10, q50, q90
        s.n, s.centres, s.sources, s.note = n, centres, sources, note

def combine(H, var, i, lead_h):
    """Distribution ponderee a l'heure i. Ne compte QUE les sources qui
    fournissent reellement la variable et qui sont dans leur portee."""
    per_centre = {}
    used, rejected = [], []
    for mid, centre, km, portee, dt, gust in SOURCES:
        if var == "wind_gusts_10m" and not gust:
            continue                                   # defaut 1 : declare
        if lead_h > portee:
            continue                                   # defaut 3 : portee respectee
        s = series(H, var, mid)
        if not s or i >= len(s) or s[i] is None:
            continue
        if var == "wind_gusts_10m":                    # garde-fou physique
            sv = series(H, "wind_speed_10m", mid)
            v = sv[i] if sv and i < len(sv) else None
            if v and v > 3:
                r = s[i] / v
                if r < GUST_RATIO_MIN or r > GUST_RATIO_MAX:
                    rejected.append("%s r=%.2f" % (mid, r))
                    continue
        w = mesh_factor(km, lead_h)
        if dt > 1 and lead_h <= 48:
            w *= 0.7                                   # defaut 5 : 3-horaire interpole
        per_centre.setdefault(centre, []).append((s[i], w, mid))
        used.append(mid)
    if not per_centre:
        return None
    # defaut 4 : un centre = une voix, repartie entre ses modeles
    pairs = []
    for centre, lst in per_centre.items():
        cw = centre_weight(centre, lead_h)
        if cw <= 0: continue
        sw = sum(w for _, w, _ in lst) or 1.0
        for v, w, _ in lst:
            pairs.append((v, cw * w / sw))
    if not pairs:
        return None
    return Point(wquantile(pairs, 0.10), wquantile(pairs, 0.50), wquantile(pairs, 0.90),
                 len(used), sorted(per_centre.keys()), used,
                 ("rejete: " + ", ".join(rejected)) if rejected else "")

def ens_quantiles(ens, var, day, h0=8, h1=20):
    """Max journalier par membre, tous ensembles confondus, un centre = une voix.
    C'est ce qui remplace le max d'un modele global isole au-dela de 48 h."""
    per_centre = {}
    for mid, (centre, data) in ens.items():
        if not data: continue
        EH = data["hourly"]
        et = [datetime.datetime.fromisoformat(t) for t in EH["time"]]
        idx = [k for k in range(len(et)) if et[k].date() == day and h0 <= et[k].hour <= h1]
        if not idx: continue
        keys = [k for k in EH.keys() if k.startswith(var)]
        vals = []
        for mk in keys:
            s = EH[mk]
            mx = max((s[k] for k in idx if k < len(s) and s[k] is not None), default=None)
            if mx is not None: vals.append(mx)
        if vals: per_centre.setdefault(centre, []).extend(vals)
    if not per_centre: return None
    pairs = []
    for centre, vals in per_centre.items():
        w = 1.0 / len(vals)                       # chaque centre pese 1, pas ses membres
        pairs += [(v, w) for v in vals]
    allv = [v for _, lst in per_centre.items() for v in lst]
    return dict(q50=wquantile(pairs, .5), q90=wquantile(pairs, .9),
                p22=100.0 * sum(1 for v in allv if v > 22) / len(allv),
                p30=100.0 * sum(1 for v in allv if v > 30) / len(allv),
                n=len(allv), centres=sorted(per_centre.keys()))

# ---------------- Ancienne methode, pour comparaison ----------------
OLD = ["meteofrance_arome_france_hd", "meteofrance_arpege_europe",
       "ecmwf_ifs025", "icon_eu", "gfs_seamless"]
OLDW = {"meteofrance_arome_france_hd": 3.0, "meteofrance_arpege_europe": 2.0,
        "ecmwf_ifs025": 2.0, "icon_eu": 1.0, "gfs_seamless": 1.0}

def old_cred_high(H, var, i):
    vals, wts = [], []
    for m in OLD:
        s = series(H, var, m)
        if s and i < len(s) and s[i] is not None:
            vals.append(s[i]); wts.append(OLDW[m])
    if not vals: return None
    pr = sorted(zip(vals, wts)); tot = sum(w for _, w in pr); acc = 0; p75 = pr[-1][0]
    for v, w in pr:
        acc += w
        if acc >= 0.75 * tot: p75 = v; break
    a = series(H, var, "meteofrance_arome_france_hd")
    av = a[i] if a and i < len(a) and a[i] is not None else None
    return max(av, p75) if av is not None else p75

def old_long(H, var, i):
    out = []
    for m in ["ecmwf_ifs025", "icon_eu", "gfs_seamless"]:
        s = series(H, var, m)
        if s and i < len(s) and s[i] is not None: out.append(s[i])
    return max(out) if out else None

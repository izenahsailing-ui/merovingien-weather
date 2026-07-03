# -*- coding: utf-8 -*-
"""IZENAH — moteur de donnees et d'analyse meteo marine.
Recupere multi-modeles + ensemble + vagues + CAPE (Open-Meteo) sur la zone
La Ciotat <-> Les Embiez, calcule plages, consensus, probabilites, confiance,
seuils Navigation, logique mouillages, detection orage. Sans cle API.
"""
import urllib.request, urllib.parse, json, time, datetime, math, os
# Heure locale FR pour l'horodatage et la logique de date (runner GitHub en UTC sinon)
os.environ.setdefault("TZ", "Europe/Paris")
try:
    time.tzset()
except Exception:
    pass

# ---------------- Points ----------------
PT_PRIMAIRE = ("La Ciotat", 43.175, 5.607)          # detail + graphe
PT_CAP_SICIE = ("Cap Sicié", 43.043, 5.858)         # acceleration
PT_MARINE   = (43.10, 5.70)                          # vagues (au large de la baie)
MOUILLAGES = {
    # Exposition selon la direction D'OU vient le vent (0 = bien abrite .. 1 = plein expose).
    # Regle locale confirmee :
    #  - La Ciotat : refuge de mistral (NW/W/N), le Bec de l'Aigle protege l'W/SW ;
    #    ouverte et dangereuse par vent d'Est/SE (le "coup d'Est" fait entrer la houle) et par le Sud.
    #  - La Madrague (St-Cyr) : refuge de vent d'Est (NE/E/SE) ; DANGEREUSE par mistral (W/NW)
    #    et par le Sud (baie des Lecques ouverte au S).
    "La Ciotat": dict(lat=43.165, lon=5.612, exp8={
        "N":0.15, "NE":0.15, "E":0.85, "SE":0.90, "S":0.70, "SW":0.45, "W":0.20, "NW":0.12}),
    "La Madrague (St-Cyr)": dict(lat=43.178, lon=5.700, exp8={
        "N":0.35, "NE":0.20, "E":0.12, "SE":0.28, "S":0.80, "SW":0.85, "W":0.90, "NW":0.92}),
}
MODELS = ["meteofrance_arome_france_hd", "meteofrance_arpege_europe", "ecmwf_ifs025", "icon_eu", "gfs_seamless"]
# Poids par modele (mailles fines credibles > modeles globaux) pour le scenario retenu
W_MODEL = {"meteofrance_arome_france_hd": 3.0, "meteofrance_arpege_europe": 2.0,
           "ecmwf_ifs025": 2.0, "icon_eu": 1.0, "gfs_seamless": 1.0}

# ---------------- Seuils Standard croisiere ----------------
S_VENT = (14, 22)      # favorable<=14 ; prudence<=22 ; sinon deconseille
S_RAF  = (20, 30)
S_MER  = (0.5, 1.25)
CAPE_ORAGE = 300       # J/kg : seuil d'instabilite a surveiller

JFR=["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
MFR=["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
def fr_date(dt): return "%s %d %s %d, %dh%02d"%(JFR[dt.weekday()],dt.day,MFR[dt.month-1],dt.year,dt.hour,dt.minute)
def fr_jour(d):  return "%s %d %s"%(JFR[d.weekday()],d.day,MFR[d.month-1])

# ---------------- HTTP ----------------
def fetch(url, timeout=25, tries=4):
    # retries patients : les runners GitHub partagent leurs IP et Open-Meteo
    # rate-limite par vagues -> on encaisse au lieu de planter
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "izenah-briefing/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e; time.sleep(2.5*(k+1))
    raise RuntimeError("fetch echec: %s -> %s" % (url[:80], last))

def om_forecast(lat, lon, days=7):
    q = dict(latitude=lat, longitude=lon, timezone="Europe/Paris",
             wind_speed_unit="kn", forecast_days=days,
             models=",".join(MODELS),
             hourly="wind_speed_10m,wind_gusts_10m,wind_direction_10m,temperature_2m,cloud_cover,pressure_msl,cape,precipitation",
             daily="sunrise,sunset")
    return fetch("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q))

def om_ensemble(lat, lon, days=12):
    q = dict(latitude=lat, longitude=lon, timezone="Europe/Paris", wind_speed_unit="kn",
             forecast_days=days, models="ecmwf_ifs025",
             hourly="wind_speed_10m,wind_gusts_10m")
    return fetch("https://ensemble-api.open-meteo.com/v1/ensemble?" + urllib.parse.urlencode(q))

def om_marine(lat, lon, days=8):
    # houle DECOMPOSEE : mer de vent (tombe avec le vent) vs houle residuelle
    # (continue d'entrer au mouillage apres le coup de vent) — decisif pour le confort de nuit
    q = dict(latitude=lat, longitude=lon, timezone="Europe/Paris", forecast_days=days,
             hourly="wave_height,wave_direction,wave_period,wind_wave_height,"
                    "swell_wave_height,swell_wave_direction,swell_wave_period,sea_surface_temperature")
    return fetch("https://marine-api.open-meteo.com/v1/marine?" + urllib.parse.urlencode(q))

# ---------------- Helpers ----------------
DIRN = ["N","NE","E","SE","S","SW","W","NW"]
def dir_card(deg):
    if deg is None: return "?"
    return ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"][int((deg%360)/22.5+0.5)%16]
def dir8(deg):
    if deg is None: return "NW"
    return DIRN[int((deg%360)/45+0.5)%8]
def in_sector(b, rng):
    if b is None: return False
    b%=360; lo,hi=rng[0]%360, rng[1]%360
    return (lo<=b<=hi) if lo<=hi else (b>=lo or b<=hi)
def moor_comfort(e, raf_max, mer_max):
    """Indice confort/risque 0..1 d'un mouillage. e = exposition directionnelle 0..1.
    Geometrie d'abord ; rafales genent partout (plus si expose) ; houle surtout si expose."""
    frac = 0.10 + 0.52*e
    frac += min(0.30, max(0.0,(raf_max-18)/60.0)) * (0.55 + 0.45*e)
    frac += min(0.25, max(0.0,(mer_max-0.6)/2.0)) * (0.25 + 0.75*e)
    return max(0.05, min(0.97, frac))
def moor_verdict(frac):
    return "Très confortable" if frac<0.35 else ("Correct" if frac<0.6 else ("Inconfortable" if frac<0.78 else "À éviter"))
def beaufort(kn):
    if kn is None: return 0
    t=[0,3,6,10,16,21,27,33,40,47,55,63]
    for i,v in enumerate(t):
        if kn<=v: return i
    return 12
def force_txt(kn): return "force %d" % beaufort(kn)
def avg(xs):
    xs=[x for x in xs if x is not None]
    return sum(xs)/len(xs) if xs else None
def col_vent(kn): return "G" if kn<=S_VENT[0] else ("A" if kn<=S_VENT[1] else "R")
def col_raf(kn):  return "G" if kn<=S_RAF[0]  else ("A" if kn<=S_RAF[1]  else "R")
def col_mer(h):   return "G" if h<=S_MER[0]   else ("A" if h<=S_MER[1]   else "R")

def series(hourly, var, model):
    return hourly.get("%s_%s" % (var, model))

def cross_stats(hourly, var, i):
    """min, max, mean across models au pas i."""
    vals=[]
    for m in MODELS:
        s=series(hourly, var, m)
        if s and i < len(s) and s[i] is not None: vals.append(s[i])
    if not vals: return (None,None,None)
    return (min(vals), max(vals), sum(vals)/len(vals))

def cred_high(hourly, var, i):
    """Scenario haut credible au pas i : max(AROME, percentile 75 pondere des modeles).
    Pour la securite nav on ne lisse jamais le danger par la moyenne."""
    vals=[]; wts=[]
    for m in MODELS:
        s=series(hourly, var, m)
        if s and i<len(s) and s[i] is not None:
            vals.append(s[i]); wts.append(W_MODEL.get(m,1.0))
    if not vals: return None
    pairs=sorted(zip(vals,wts)); tot=sum(w for _,w in pairs); acc=0; p75=pairs[-1][0]
    for v,w in pairs:
        acc+=w
        if acc>=0.75*tot: p75=v; break
    a=series(hourly, var, "meteofrance_arome_france_hd")
    av=a[i] if a and i<len(a) and a[i] is not None else None
    return max(av,p75) if av is not None else p75

def _run_stability(target_day, vent_hi, raf_max, dom_dir):
    """Stabilite run-a-run : compare la prevision du jour au brief archive le plus
    recent qui parlait deja du meme jour cible (le J+2 d'hier = notre J+1).
    Renvoie (score 0..1, note)."""
    base=os.path.dirname(os.path.abspath(__file__)); arch=os.path.join(base,"archives")
    try:
        cand=[f for f in os.listdir(arch) if f.startswith("brief") and f.endswith(".json")]
        cand=[f for f in cand if time.time()-os.path.getmtime(os.path.join(arch,f))>600]
        cand.sort(key=lambda f:os.path.getmtime(os.path.join(arch,f)), reverse=True)
        for f in cand[:5]:
            try: d=json.load(open(os.path.join(arch,f)))
            except Exception: continue
            for c in d.get("consensus",[]):
                if c.get("day")==fr_jour(target_day):
                    dv=abs((c.get("vmax") or 0)-vent_hi)
                    dg=abs((c.get("gust") or raf_max)-raf_max)
                    ddir=0 if c.get("wdir")==dom_dir else 1
                    s=max(0.0,min(1.0,1.0-dv/15.0-dg/30.0-0.15*ddir))
                    return s,("stable vs veille" if s>=0.75 else "a bougé depuis hier")
        return 0.75,"pas d'historique comparable"
    except Exception:
        return 0.75,"pas d'historique comparable"

def primary_series(hourly, var):
    """AROME si dispo sinon ECMWF, par pas (pour le detail)."""
    a=series(hourly, var, "meteofrance_arome_france_hd")
    e=series(hourly, var, "ecmwf_ifs025")
    n=len(hourly["time"]); out=[]
    for i in range(n):
        v=None
        if a and i<len(a) and a[i] is not None: v=a[i]
        elif e and i<len(e) and e[i] is not None: v=e[i]
        out.append(v)
    return out

# ---------------- Analyse principale ----------------
def build_brief(target="demain"):
    now=datetime.datetime.now()
    fc=om_forecast(*PT_PRIMAIRE[1:], days=10)
    cap=om_forecast(*PT_CAP_SICIE[1:], days=2)
    ens=om_ensemble(*PT_PRIMAIRE[1:], days=12)
    mar=om_marine(*PT_MARINE, days=8)
    # BMS officiel recupere TOT : il PILOTE le feu, les fenetres et la fiabilite sur sa validite
    try:
        import izenah_bms_officiel
        bms_off=izenah_bms_officiel.fetch_bms()
    except Exception:
        bms_off=None
    def in_bms(dt):
        """L'heure dt tombe-t-elle dans la fenetre de validite du BMS officiel de NOTRE zone ?"""
        if not (bms_off and bms_off.get("actif_zone")): return False
        try:
            d0=datetime.datetime.fromisoformat(bms_off["debut_iso"]) if bms_off.get("debut_iso") else now
            d1=datetime.datetime.fromisoformat(bms_off["fin_iso"]) if bms_off.get("fin_iso") else now
            return d0<=dt<=d1
        except Exception:
            return False

    H=fc["hourly"]; times=[datetime.datetime.fromisoformat(t) for t in H["time"]]
    n=len(times)
    # index de "ce soir" (maintenant) -> +24h
    i_now=max(0, min(range(n), key=lambda i: abs((times[i]-now).total_seconds())))
    # marine aligne par index (memes timezones, pas horaire)
    MH=mar["hourly"]; wav_h=MH["wave_height"]; wav_d=MH["wave_direction"]; wav_p=MH["wave_period"]
    wav_sst=MH.get("sea_surface_temperature",[])
    swl_h=MH.get("swell_wave_height",[]); swl_d=MH.get("swell_wave_direction",[])
    wwv_h=MH.get("wind_wave_height",[])

    arome_dir=primary_series(H,"wind_direction_10m")
    arome_cloud=primary_series(H,"cloud_cover")
    arome_cape=primary_series(H,"cape")
    arome_press=primary_series(H,"pressure_msl")
    arome_temp=primary_series(H,"temperature_2m")

    # --- fenetre d'affichage : le JOUR CIBLE en entier, plus la nuit qui y mene ---
    # (le badge Navigation, le graphe et le tableau parlent ainsi du MEME jour)
    target_day=(now.date() if target=="today" else (now+datetime.timedelta(days=1)).date())
    win_start=max(now-datetime.timedelta(hours=1),
                  datetime.datetime.combine(target_day, datetime.time(0))-datetime.timedelta(hours=6))
    win_end=datetime.datetime.combine(target_day, datetime.time(23))
    idx_win=[i for i in range(n) if win_start<=times[i]<=win_end][:32]
    if not idx_win: idx_win=list(range(i_now, min(n, i_now+25)))

    chart=dict(hours=[], mean=[], mn=[], mx=[], gust=[], night=[], dir=[])
    sun=fc.get("daily",{})
    def is_night(dt):
        # approx: nuit avant 6h ou apres 21h (ete) ; affine via sunrise/sunset si dispo
        try:
            srises=[datetime.datetime.fromisoformat(x) for x in sun["sunrise"]]
            ssets =[datetime.datetime.fromisoformat(x) for x in sun["sunset"]]
            d=dt.date()
            sr=next((s for s in srises if s.date()==d), None)
            sscur=next((s for s in ssets if s.date()==d), None)
            if sr and sscur: return not (sr <= dt <= sscur)
        except Exception: pass
        return dt.hour<6 or dt.hour>=21
    for i in idx_win:
        mn,mx,mean=cross_stats(H,"wind_speed_10m",i)
        _,gmax,_=cross_stats(H,"wind_gusts_10m",i)
        if mean is None: continue
        chart["hours"].append(times[i].strftime("%Hh"))
        chart["mean"].append(round(mean)); chart["mn"].append(round(mn)); chart["mx"].append(round(mx))
        chart["gust"].append(round(gmax) if gmax else round(mean*1.5))
        chart["night"].append(is_night(times[i]))
        chart["dir"].append(dir8(arome_dir[i]))

    # --- detail sur la meme fenetre (cadence 2h, 3h si la fenetre est longue) ---
    detail=[]
    step=2 if len(idx_win)<=26 else 3
    for k in range(0, len(idx_win), step):
        i=idx_win[k]
        mn,mx,mean=cross_stats(H,"wind_speed_10m",i)
        _,gmax,_=cross_stats(H,"wind_gusts_10m",i)
        if mean is None: continue
        d=arome_dir[i]; wd=dir8(d)
        wh=wav_h[i] if i<len(wav_h) and wav_h[i] is not None else None
        wdir=dir8(wav_d[i]) if i<len(wav_d) and wav_d[i] is not None else "?"
        wp=wav_p[i] if i<len(wav_p) and wav_p[i] is not None else None
        cl=arome_cloud[i] or 0
        ciel = "moon" if is_night(times[i]) else ("sun" if cl<35 else ("few" if cl<70 else "cloud"))
        ciel_lbl = "Clair" if cl<35 else ("Peu nuageux" if cl<70 else "Couvert")
        detail.append(dict(
            hh=times[i].strftime("%Hh"), night=is_night(times[i]), wdir=wd,
            vmin=round(mn), vmax=round(mx), mean=round(mean), force=force_txt(mean),
            gust=round(gmax) if gmax else round(mean*1.5),
            houle_dir=wdir, houle=("%.1f m"%wh).replace(".",",") if wh is not None else "n/d",
            houle_p=("%d s"%round(wp)) if wp else "",
            mer=round(wh,1) if wh is not None else None,
            air=round(arome_temp[i]) if arome_temp[i] is not None else None,
            eau=round(wav_sst[i]) if i<len(wav_sst) and wav_sst[i] is not None else None,
            cloud=round(cl), ciel=ciel, ciel_lbl=ciel_lbl,
            press=round(arome_press[i]) if arome_press[i] is not None else None,
            cape=round(arome_cape[i]) if arome_cape[i] is not None else 0,
        ))

    # --- jour cible : fenetre journee pour Navigation ---
    tomorrow=target_day
    idx_tom=[i for i in range(n) if times[i].date()==tomorrow]
    day_idx=[i for i in idx_tom if 8<=times[i].hour<=20]
    # scenario haut credible (jamais la moyenne : elle lisse le danger)
    vent_hi = max((cred_high(H,"wind_speed_10m",i) or 0) for i in day_idx) if day_idx else 0
    i_peak  = max(day_idx, key=lambda i:(cred_high(H,"wind_speed_10m",i) or 0)) if day_idx else None
    v_lo,v_hi,_ = cross_stats(H,"wind_speed_10m",i_peak) if i_peak is not None else (0,0,0)
    vent_max_moy = vent_hi
    # rafales J+1 : scenario haut credible (AROME pondere x3 / p75), PAS le pire
    # modele global isole — a moins de 48 h, la maille fine fait foi
    raf_max      = max((cred_high(H,"wind_gusts_10m",i) or 0) for i in day_idx) if day_idx else 0
    mer_max      = max((wav_h[i] for i in idx_tom if i<len(wav_h) and wav_h[i] is not None), default=0)
    # mer de vent vs houle residuelle : une houle longue sans vent n'est pas un danger
    wwv_max      = max((wwv_h[i] for i in day_idx if i<len(wwv_h) and wwv_h[i] is not None), default=0) if day_idx else 0
    mer_soft     = (wwv_max < 0.3 and raf_max <= 20)
    cape_max     = max((arome_cape[i] or 0) for i in idx_tom) if idx_tom else 0
    # Cap Sicie : surcote
    capH=cap["hourly"]; cs_idx=[i for i in range(len(capH["time"])) if datetime.datetime.fromisoformat(capH["time"][i]).date()==tomorrow and 8<=datetime.datetime.fromisoformat(capH["time"][i]).hour<=20]
    cs_gust=max((capH["wind_gusts_10m_meteofrance_arome_france_hd"][i] for i in cs_idx if i<len(capH.get("wind_gusts_10m_meteofrance_arome_france_hd",[])) and capH["wind_gusts_10m_meteofrance_arome_france_hd"][i] is not None), default=0) if cs_idx else 0

    def feu(vent,raf,mer,cape,soft=False):
        # soft=True (J+1 seulement) : houle longue residuelle toleree jusqu'a 1,0 m
        cm=("G" if mer<=1.0 else ("A" if mer<=1.25 else "R")) if soft else col_mer(mer)
        c="G"
        for x in (col_vent(vent),col_raf(raf),cm):
            if x=="A" and c=="G": c="A"
            if x=="R": c="R"
        if cape>=CAPE_ORAGE and c=="G": c="A"
        return c
    fc_color=feu(vent_max_moy,raf_max,mer_max,cape_max,soft=mer_soft)
    # Le BMS officiel FAIT FOI : s'il couvre une partie de la journee cible,
    # le feu ne peut pas etre meilleur que Prudence (Deconseille si coup de vent+).
    bms_on_target=any(in_bms(times[i]) for i in day_idx) if day_idx else False
    if bms_on_target:
        force_col="R" if (bms_off or {}).get("grave") else "A"
        order={"G":0,"A":1,"R":2}
        if order[force_col]>order[fc_color]: fc_color=force_col
    nav_status={"G":"FAVORABLE","A":"PRUDENCE","R":"DÉCONSEILLÉ"}[fc_color]
    dom_dir=dir8(avg([arome_dir[i] for i in day_idx])) if day_idx else "NW"
    if v_lo is not None and v_hi is not None and round(v_lo)!=round(v_hi):
        nav_reason="Vent %s, %d à %d kn selon les modèles (rafales %d). Mer %.1f m." % (dom_dir, round(v_lo), round(max(v_hi,vent_hi)), round(raf_max), mer_max)
    else:
        nav_reason="Vent %s, jusqu'à %d kn (rafales %d). Mer %.1f m." % (dom_dir, round(vent_hi), round(raf_max), mer_max)
    if cs_gust>raf_max+3: nav_reason+=" Accélération au Cap Sicié (rafales %d kn)." % round(cs_gust)
    if bms_on_target: nav_reason+=" BMS officiel en cours sur ce créneau (il fait foi)."

    # --- probabilites d'ensemble (J+1 et au-dela) ---
    EH=ens["hourly"]; et=[datetime.datetime.fromisoformat(t) for t in EH["time"]]
    def members(var):
        base=[k for k in EH.keys() if k.startswith(var)]
        return base
    gust_members=[k for k in EH.keys() if k.startswith("wind_gusts_10m")]
    def proba_over(day, var_prefix, thr, members_keys):
        idx=[i for i in range(len(et)) if et[i].date()==day and 8<=et[i].hour<=20]
        if not idx or not members_keys: return None
        cnt=0; tot=0
        for mk in members_keys:
            s=EH[mk];
            mx=max((s[i] for i in idx if i<len(s) and s[i] is not None), default=None)
            if mx is None: continue
            tot+=1; cnt+= (1 if mx>thr else 0)
        return round(100*cnt/tot) if tot else None
    p_raf30_tom=proba_over(tomorrow,"wind_gusts_10m",30,gust_members)

    # --- fiabilite J+1 : score 0..100 = accord modeles x accord ensemble x stabilite run-a-run ---
    # Les ecarts sont mesures en % du vent prevu (5 kn d'ecart sur 25 kn de mistral
    # n'est pas la meme incertitude que 5 kn sur 8 kn de brise).
    rels=[]
    for i in day_idx:
        mn,mx,mean=cross_stats(H,"wind_speed_10m",i)
        if mn is not None and mean is not None: rels.append((mx-mn)/max(mean,10.0))
    rel_spread=avg(rels) or 0
    ens_idx=[i for i in range(len(et)) if et[i].date()==tomorrow and 8<=et[i].hour<=20]
    member_max=[]
    for mk in [k for k in EH.keys() if k.startswith("wind_speed_10m")]:
        s=EH[mk]; mx=max((s[i] for i in ens_idx if i<len(s) and s[i] is not None), default=None)
        if mx is not None: member_max.append(mx)
    ens_std=(statistics_std(member_max)) if len(member_max)>2 else 0
    ens_mean=avg(member_max) or 0
    rel_std=ens_std/max(ens_mean,10.0)
    s_mod=max(0.0,min(1.0,1.15-1.1*rel_spread))
    s_ens=max(0.0,min(1.0,1.10-2.0*rel_std))
    s_run,run_note=_run_stability(tomorrow, vent_hi, raf_max, dom_dir)
    conf_pct=int(round(100*(0.40*s_mod+0.35*s_ens+0.25*s_run)))
    # confrontation au BMS officiel (il fait foi) :
    if bms_on_target and raf_max<30:
        conf_pct=min(conf_pct,55); run_note="bulletin officiel plus sévère que les modèles"
    elif bms_on_target:
        conf_pct=min(100,conf_pct+10); run_note="confirmé par le BMS officiel"
    conf="ÉLEVÉE" if conf_pct>=70 else ("MODÉRÉE" if conf_pct>=50 else "FAIBLE")
    conf_detail="Modèles d'accord à %d%% · scénarios à %d%% · %s"%(round(100*s_mod),round(100*s_ens),run_note)

    # --- mouillages : confort/risque a partir de l'exposition directionnelle (toutes directions) ---
    moor=[]
    for name,info in MOUILLAGES.items():
        e=info["exp8"].get(dom_dir,0.5)
        frac=moor_comfort(e, raf_max, mer_max)
        moor.append(dict(name=name, frac=round(frac,2), verdict=moor_verdict(frac),
                         protected=(e<=0.33), exposed=(e>=0.60), expo_dir=round(e,2)))
    best=min(moor, key=lambda m:m["frac"])["name"]
    # bascule : dans les 48 h, le meilleur mouillage devient-il expose alors que l'autre est abrite ?
    bascule=None
    best_info=MOUILLAGES[best]; other=[k for k in MOUILLAGES if k!=best][0]; other_info=MOUILLAGES[other]
    for i in range(n):
        if not (0 <= (times[i]-now).total_seconds() <= 48*3600): continue
        dvals=[series(H,"wind_direction_10m",m)[i] for m in MODELS
               if series(H,"wind_direction_10m",m) and i<len(series(H,"wind_direction_10m",m)) and series(H,"wind_direction_10m",m)[i] is not None]
        dd=avg(dvals); _,_,vmean=cross_stats(H,"wind_speed_10m",i)
        if dd is None or (vmean or 0)<12: continue
        d8=dir8(dd); e_best=best_info["exp8"].get(d8,0.5); e_other=other_info["exp8"].get(d8,0.5)
        if e_best>=0.60 and e_other<=0.40 and (e_best-e_other)>=0.30:
            jour=("aujourd'hui" if times[i].date()==now.date()
                  else ("demain" if times[i].date()==(now+datetime.timedelta(days=1)).date() else fr_jour(times[i].date())))
            bascule=dict(to=other, jour=jour, heure=times[i].strftime("%Hh"), dir=d8); break

    # --- mouillages NUIT PAR NUIT : ou dormir ce soir, ou dormir demain soir ---
    def moor_comfort_hour(info, i):
        """Confort/risque du mouillage a l'heure i : vent (rafales) + mer totale selon
        l'exposition au vent, PLUS la houle residuelle (swell) qui entre au mouillage
        meme apres la tombee du vent, selon l'exposition a SA direction."""
        dd=arome_dir[i]
        e_w=info["exp8"].get(dir8(dd),0.5) if dd is not None else 0.5
        _,g,_=cross_stats(H,"wind_gusts_10m",i); g=g or 0
        wh=wav_h[i] if i<len(wav_h) and wav_h[i] is not None else 0
        frac=moor_comfort(e_w,g,wh)
        sh=swl_h[i] if i<len(swl_h) and swl_h[i] is not None else 0
        sd=swl_d[i] if i<len(swl_d) and swl_d[i] is not None else None
        if sh>=0.4 and sd is not None:
            e_s=info["exp8"].get(dir8(sd),0.5)
            frac=min(0.97, frac+min(0.25,(sh-0.3)/2.0)*e_s)
        return frac
    def night_idx(d0):
        a=datetime.datetime.combine(d0, datetime.time(20)); b=a+datetime.timedelta(hours=12)
        return [i for i in range(n) if a<=times[i]<=b]
    nights=[]
    for lbl,d0 in (("cette nuit", now.date()), ("demain nuit", now.date()+datetime.timedelta(days=1))):
        idxN=night_idx(d0)
        if not idxN: continue
        per={}
        for name,info in MOUILLAGES.items():
            per[name]=round(max(moor_comfort_hour(info,i) for i in idxN),2)
        # les DEUX mouillages sont presentes a egalite (aucun favori fixe) :
        # classes par confort, "au choix" si l'ecart est negligeable
        ranked=sorted(per.items(), key=lambda kv: kv[1])
        (n1,f1),(n2,f2)=ranked[0],ranked[1]
        nights.append(dict(label=lbl, best=n1, frac=f1, verdict=moor_verdict(f1),
                           alt=n2, alt_frac=f2, alt_verdict=moor_verdict(f2),
                           equal=(abs(f2-f1)<0.07), per=per,
                           port=(f1>=0.78)))  # aucun abri serein -> port conseille
    moor_change=None
    if len(nights)==2 and nights[0]["best"]!=nights[1]["best"]:
        moor_change=dict(frm=nights[0]["best"], to=nights[1]["best"],
                         quand=(("%s vers %s (vent passant %s)"%(bascule["jour"],bascule["heure"],bascule["dir"]))
                                if bascule and bascule.get("to")==nights[1]["best"] else "demain dans la journée"))

    # --- consensus J+2..J+5 (modeles globaux) ---
    longmodels=["ecmwf_ifs025","icon_eu","gfs_seamless"]
    def cross_long(var,i):
        out=[]
        for m in longmodels:
            s=series(H,var,m)
            if s and i<len(s) and s[i] is not None: out.append(s[i])
        return out
    consensus=[]
    for dd in range(2,6):
        day=(now+datetime.timedelta(days=dd)).date()
        idx=[i for i in range(n) if times[i].date()==day and 8<=times[i].hour<=18]
        if not idx: continue
        vmins=[];vmaxs=[];gusts=[];dirs=[];spreads2=[]
        for i in idx:
            v=cross_long("wind_speed_10m",i)
            if v: vmins.append(min(v)); vmaxs.append(max(v)); spreads2.append((max(v)-min(v))/max(sum(v)/len(v),10.0))
            g=cross_long("wind_gusts_10m",i)
            if g: gusts.append(max(g))
            d=cross_long("wind_direction_10m",i)
            if d: dirs.append(avg(d))
        if not vmaxs: continue
        vmin=round(min(vmins)); vmax=round(max(vmaxs)); f1,f2=beaufort(vmin),beaufort(vmax)
        force=("force %d"%f2) if f1==f2 else ("force %d à %d"%(f1,f2))
        mer=max((wav_h[i] for i in idx if i<len(wav_h) and wav_h[i] is not None), default=None)
        hdir=dir8(avg([wav_d[i] for i in idx if i<len(wav_d) and wav_d[i] is not None])) if idx else "?"
        sp=avg(spreads2) or 0
        pct_c=int(round(100*max(0.0,min(1.0,1.15-1.1*sp))))
        gmax_day=round(max(gusts)) if gusts else None
        consensus.append(dict(day=fr_jour(day), wdir=dir8(avg(dirs)) if dirs else "?",
            vmin=vmin, vmax=vmax, force=force, gust=gmax_day,
            houle_dir=hdir, houle=("%.1f m"%mer).replace(".",",") if mer is not None else "n/d",
            nav=feu(vmax, gmax_day or 0, mer or 0, 0),
            conf_pct=pct_c, conf="Élevée"))
    # coherence : la confiance ne peut pas AUGMENTER en s'eloignant dans le temps
    prev=conf_pct
    for c in consensus:
        c["conf_pct"]=min(c["conf_pct"], prev); prev=c["conf_pct"]
        c["conf"]="Élevée" if c["conf_pct"]>=70 else ("Modérée" if c["conf_pct"]>=50 else "Faible")
    # --- tendance J+5..J+12 (ensemble) ---
    def proba_window(d0,d1,thr):
        days={(now+datetime.timedelta(days=x)).date() for x in range(d0,d1+1)}
        keys=[k for k in EH.keys() if k.startswith("wind_gusts_10m")]
        if not keys: return None
        tot=0;cnt=0
        for mk in keys:
            s=EH[mk]; mx=None
            for i in range(len(et)):
                if et[i].date() in days and 8<=et[i].hour<=18 and i<len(s) and s[i] is not None:
                    mx=s[i] if mx is None else max(mx,s[i])
            if mx is None: continue
            tot+=1; cnt+=(1 if mx>thr else 0)
        return (round(100*cnt/tot) if tot else None)
    tendance=[]
    p1=proba_window(5,7,22); p2=proba_window(8,12,33)
    if p1 is not None: tendance.append(("Vent fort (> force 6) entre J+5 et J+7", p1/100.0))
    if p2 is not None: tendance.append(("Coup de vent (> force 7) au-delà de J+8", p2/100.0))

    # --- fenetres de sortie sur le jour cible (8h-20h) ---
    def hour_feu(i):
        v=cred_high(H,"wind_speed_10m",i) or 0
        g=cred_high(H,"wind_gusts_10m",i) or 0
        w=wav_h[i] if i<len(wav_h) and wav_h[i] is not None else 0
        ww=wwv_h[i] if i<len(wwv_h) and wwv_h[i] is not None else 0
        soft=(ww<0.3 and g<=20)
        cm=("G" if w<=1.0 else ("A" if w<=1.25 else "R")) if soft else col_mer(w)
        cols=(col_vent(v),col_raf(g),cm)
        f="R" if "R" in cols else ("A" if "A" in cols else "G")
        # pendant la validite d'un BMS officiel, jamais mieux que Prudence
        if in_bms(times[i]):
            f="R" if (bms_off or {}).get("grave") else ("A" if f=="G" else f)
        return f
    fenetre=None
    for want in ("G","A"):
        best_run=[]; run=[]
        for i in day_idx:
            f=hour_feu(i)
            ok=(f=="G") if want=="G" else (f in ("G","A"))
            if ok: run.append(i)
            else:
                if len(run)>len(best_run): best_run=run
                run=[]
        if len(run)>len(best_run): best_run=run
        if len(best_run)>=3:
            if want=="G" and len(best_run)>=len(day_idx)-1:
                fenetre=dict(kind="ALL", frm="", to="")
            else:
                fenetre=dict(kind=want, frm=times[best_run[0]].strftime("%Hh"), to=times[best_run[-1]].strftime("%Hh"))
            break

    # --- contexte synoptique (une ligne de lecture meteo) ---
    v_am=avg([cross_stats(H,"wind_speed_10m",i)[2] for i in day_idx if times[i].hour<=12]) or 0
    v_pm=avg([cross_stats(H,"wind_speed_10m",i)[2] for i in day_idx if times[i].hour>=15]) or 0
    trend=(" en renforcement" if v_pm>v_am+4 else (" en déclin" if v_am>v_pm+4 else " établi"))
    if vent_hi>=15 and dom_dir in ("NW","W","N"): contexte="Mistral"+trend
    elif vent_hi>=15 and dom_dir in ("E","SE","NE"): contexte="Épisode de vent d'Est"+trend
    elif vent_hi>=15: contexte="Flux de secteur %s soutenu"%dom_dir+trend
    elif vent_hi<10: contexte="Situation calme, brises thermiques dominantes"
    else: contexte="Flux modéré de %s"%dom_dir
    if cape_max>=CAPE_ORAGE: contexte+=", atmosphère instable (grains possibles)"

    # estimation BMS : Meteo-France emet un BMS Cote des force 7 (28 kn soutenu) ;
    # les rafales 34-40 kn = coup de vent. On declenche sur les rafales ET le vent max (pas la moyenne lissee).
    bms_est = ("coup de vent" if (raf_max >= 40 or vent_max_moy >= 34)
               else ("grand frais à coup de vent" if (raf_max >= 34 or vent_max_moy >= 28) else None))
    try:
        import izenah_vigilance
        vigilance = izenah_vigilance.fetch_vigilance()
    except Exception:
        vigilance = None
    # bms_off deja recupere en tete de fonction (il pilote feu/fenetres/fiabilite)

    brief=dict(
        generated=fr_date(now),
        target=target,
        bms_est=bms_est,
        bms_officiel=bms_off,
        vigilance=vigilance,
        i_now=i_now, n=n,
        chart=chart, detail=detail,
        nav=dict(color=fc_color, status=nav_status, reason=nav_reason),
        confiance=conf, confiance_pct=conf_pct, conf_detail=conf_detail,
        fenetre=fenetre, contexte=contexte, target_day=tomorrow.isoformat(),
        dom_dir=dom_dir, vent_lo=round(v_lo or 0),
        vent_max=round(vent_max_moy), raf_max=round(raf_max), mer_max=round(mer_max,1),
        cape_max=round(cape_max), cs_gust=round(cs_gust),
        p_raf30_tom=p_raf30_tom,
        mouillages=moor, mouillage_best=best, mouillage_bascule=bascule,
        nuits=nights, moor_change=moor_change,
        orage=("élevé" if cape_max>=800 else ("modéré" if cape_max>=CAPE_ORAGE else "faible")),
        consensus=consensus, tendance=tendance,
    )
    return brief

def deg_from(card):
    return {"N":0,"NE":45,"E":90,"SE":135,"S":180,"SW":225,"W":270,"NW":315}.get(card,315)
def statistics_std(xs):
    if len(xs)<2: return 0
    m=sum(xs)/len(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))

if __name__=="__main__":
    import locale
    try: locale.setlocale(locale.LC_TIME,"fr_FR.UTF-8")
    except Exception: pass
    b=build_brief()
    print("== BRIEFING IZENAH (test moteur) ==")
    print("Genere:", b["generated"])
    print("Navigation demain:", b["nav"]["status"], "|", b["nav"]["reason"])
    print("Confiance:", b["confiance"], "| vent_max %d kn, rafales %d, mer %.1f m, CAPE %d"%(b["vent_max"],b["raf_max"],b["mer_max"],b["cape_max"]))
    print("P(rafales>30kn) demain:", b["p_raf30_tom"], "%")
    print("Orage:", b["orage"], "| Cap Sicié rafales:", b["cs_gust"], "kn")
    print("Mouillage conseillé:", b["mouillage_best"])
    for m in b["mouillages"]:
        print("  -", m["name"], "confort=%.2f"%m["frac"], m["verdict"], "(protégé)" if m["protected"] else ("(exposé)" if m["exposed"] else ""))
    print("Graphe: %d points horaires, ex mean[0:6]=%s" % (len(b["chart"]["mean"]), b["chart"]["mean"][:6]))
    print("Détail 2h: %d lignes, 1ere=%s" % (len(b["detail"]), {k:b["detail"][0][k] for k in ("hh","wdir","vmin","vmax","gust","mer","eau","press")} if b["detail"] else None))
    print("Consensus J+2..J+4:")
    for c in b["consensus"]:
        print("   %s : %s %d à %d kn (%s), rafales %s, houle %s, confiance %s"%(c["day"],c["wdir"],c["vmin"],c["vmax"],c["force"],c["gust"],c["houle"],c["conf"]))
    print("Tendance:")
    for label,frac in b["tendance"]:
        print("   %s : %d%%"%(label,round(frac*100)))

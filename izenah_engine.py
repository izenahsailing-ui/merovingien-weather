# -*- coding: utf-8 -*-
"""IZENAH — moteur de donnees et d'analyse meteo marine.
Recupere multi-modeles + ensemble + vagues + CAPE (Open-Meteo) sur la zone
La Ciotat <-> Les Embiez, calcule plages, consensus, probabilites, confiance,
seuils Navigation, logique mouillages, detection orage. Sans cle API.
"""
import urllib.request, urllib.parse, json, time, datetime, math

# ---------------- Points ----------------
PT_PRIMAIRE = ("La Ciotat", 43.175, 5.607)          # detail + graphe
PT_CAP_SICIE = ("Cap Sicié", 43.043, 5.858)         # acceleration
PT_MARINE   = (43.10, 5.70)                          # vagues (au large de la baie)
MOUILLAGES = {
    "La Ciotat":            dict(lat=43.165, lon=5.612, prot=(280,40),  expo=(90,200)),
    "La Madrague (St-Cyr)": dict(lat=43.178, lon=5.700, prot=(60,170),  expo=(185,260), prot2=(300,340)),
}
MODELS = ["meteofrance_arome_france_hd", "ecmwf_ifs025", "icon_eu", "gfs_seamless"]

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
def fetch(url, timeout=20, tries=3):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "izenah-briefing/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e; time.sleep(1.5*(k+1))
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

def om_marine(lat, lon, days=5):
    q = dict(latitude=lat, longitude=lon, timezone="Europe/Paris", forecast_days=days,
             hourly="wave_height,wave_direction,wave_period,sea_surface_temperature")
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
def build_brief():
    now=datetime.datetime.now()
    fc=om_forecast(*PT_PRIMAIRE[1:], days=7)
    cap=om_forecast(*PT_CAP_SICIE[1:], days=2)
    ens=om_ensemble(*PT_PRIMAIRE[1:], days=12)
    mar=om_marine(*PT_MARINE, days=5)

    H=fc["hourly"]; times=[datetime.datetime.fromisoformat(t) for t in H["time"]]
    n=len(times)
    # index de "ce soir" (maintenant) -> +24h
    i_now=max(0, min(range(n), key=lambda i: abs((times[i]-now).total_seconds())))
    # marine aligne par index (memes timezones, pas horaire)
    MH=mar["hourly"]; wav_h=MH["wave_height"]; wav_d=MH["wave_direction"]; wav_p=MH["wave_period"]
    wav_sst=MH.get("sea_surface_temperature",[])

    arome_dir=primary_series(H,"wind_direction_10m")
    arome_cloud=primary_series(H,"cloud_cover")
    arome_cape=primary_series(H,"cape")
    arome_press=primary_series(H,"pressure_msl")
    arome_temp=primary_series(H,"temperature_2m")

    # --- graphe horaire 24h (a partir de i_now) ---
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
    for k in range(0, 25):
        i=i_now+k
        if i>=n: break
        mn,mx,mean=cross_stats(H,"wind_speed_10m",i)
        _,gmax,_=cross_stats(H,"wind_gusts_10m",i)
        if mean is None: continue
        chart["hours"].append(times[i].strftime("%Hh"))
        chart["mean"].append(round(mean)); chart["mn"].append(round(mn)); chart["mx"].append(round(mx))
        chart["gust"].append(round(gmax) if gmax else round(mean*1.5))
        chart["night"].append(is_night(times[i]))
        chart["dir"].append(dir8(arome_dir[i]))

    # --- detail 2h sur 24h ---
    detail=[]
    for k in range(0, 25, 2):
        i=i_now+k
        if i>=n: break
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

    # --- demain (J+1) : fenetre journee pour Navigation ---
    tomorrow=(now+datetime.timedelta(days=1)).date()
    idx_tom=[i for i in range(n) if times[i].date()==tomorrow]
    day_idx=[i for i in idx_tom if 8<=times[i].hour<=20]
    vent_max_moy = max((cross_stats(H,"wind_speed_10m",i)[2] or 0) for i in day_idx) if day_idx else 0
    raf_max      = max((cross_stats(H,"wind_gusts_10m",i)[1] or 0) for i in day_idx) if day_idx else 0
    mer_max      = max((wav_h[i] for i in idx_tom if i<len(wav_h) and wav_h[i] is not None), default=0)
    cape_max     = max((arome_cape[i] or 0) for i in idx_tom) if idx_tom else 0
    # Cap Sicie : surcote
    capH=cap["hourly"]; cs_idx=[i for i in range(len(capH["time"])) if datetime.datetime.fromisoformat(capH["time"][i]).date()==tomorrow and 8<=datetime.datetime.fromisoformat(capH["time"][i]).hour<=20]
    cs_gust=max((capH["wind_gusts_10m_meteofrance_arome_france_hd"][i] for i in cs_idx if i<len(capH.get("wind_gusts_10m_meteofrance_arome_france_hd",[])) and capH["wind_gusts_10m_meteofrance_arome_france_hd"][i] is not None), default=0) if cs_idx else 0

    def feu(vent,raf,mer,cape):
        c="G"
        for x in (col_vent(vent),col_raf(raf),col_mer(mer)):
            if x=="A" and c=="G": c="A"
            if x=="R": c="R"
        if cape>=CAPE_ORAGE and c=="G": c="A"
        return c
    fc_color=feu(vent_max_moy,raf_max,mer_max,cape_max)
    nav_status={"G":"FAVORABLE","A":"PRUDENCE","R":"DÉCONSEILLÉ"}[fc_color]
    dom_dir=dir8(avg([arome_dir[i] for i in day_idx])) if day_idx else "NW"
    nav_reason="Vent %s dominant, jusqu'à %d kn (rafales %d). Mer %.1f m." % (dom_dir, round(vent_max_moy), round(raf_max), mer_max)
    if cs_gust>raf_max+3: nav_reason+=" Accélération au Cap Sicié (rafales %d kn)." % round(cs_gust)

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

    # --- confiance J+1 : accord modeles + dispersion ensemble ---
    spreads=[]
    for i in day_idx:
        mn,mx,mean=cross_stats(H,"wind_speed_10m",i)
        if mn is not None: spreads.append(mx-mn)
    model_spread=avg(spreads) or 0
    # dispersion ensemble (ecart-type des max journaliers)
    ens_idx=[i for i in range(len(et)) if et[i].date()==tomorrow and 8<=et[i].hour<=20]
    member_max=[]
    for mk in [k for k in EH.keys() if k.startswith("wind_speed_10m")]:
        s=EH[mk]; mx=max((s[i] for i in ens_idx if i<len(s) and s[i] is not None), default=None)
        if mx is not None: member_max.append(mx)
    ens_std=(statistics_std(member_max)) if len(member_max)>2 else 0
    if model_spread<5 and ens_std<4: conf="ÉLEVÉE"
    elif model_spread<10 and ens_std<7: conf="MODÉRÉE"
    else: conf="FAIBLE"

    # --- mouillages ---
    moor=[]
    for name,info in MOUILLAGES.items():
        protected = in_sector(deg_from(dom_dir), info["prot"]) or in_sector(deg_from(dom_dir), info.get("prot2",(999,999)))
        exposed   = in_sector(deg_from(dom_dir), info["expo"])
        if protected:
            base=0.12 + min(0.30, max(0,(raf_max-18)/60.0))     # protege : surtout les rafales genent
        elif exposed:
            base=0.62 + min(0.30, max(0,(mer_max-0.6)/2.0))     # expose : la houle entre
        else:
            base=0.42 + min(0.20, max(0,(vent_max_moy-12)/40.0))
        if name.startswith("La Ciotat") and dom_dir in ("NW","N","W"): base-=0.05  # reference Mistral
        frac=max(0.05,min(0.95,base))
        verdict = "Très confortable" if frac<0.35 else ("Correct" if frac<0.6 else ("Inconfortable" if frac<0.78 else "À éviter"))
        moor.append(dict(name=name, frac=round(frac,2), verdict=verdict,
                         protected=protected, exposed=exposed))
    best=min(moor, key=lambda m:m["frac"])["name"]
    # bascule : le vent entre-t-il dans le secteur EXPOSÉ du meilleur mouillage dans les 48 h ?
    bascule=None
    exposed_sec=MOUILLAGES[best]["expo"]
    other=[k for k in MOUILLAGES if k!=best][0]
    for i in range(n):
        if not (0 <= (times[i]-now).total_seconds() <= 48*3600): continue
        dvals=[series(H,"wind_direction_10m",m)[i] for m in MODELS
               if series(H,"wind_direction_10m",m) and i<len(series(H,"wind_direction_10m",m)) and series(H,"wind_direction_10m",m)[i] is not None]
        dd=avg(dvals); _,_,vmean=cross_stats(H,"wind_speed_10m",i)
        if dd is not None and (vmean or 0)>=10 and in_sector(dd, exposed_sec):
            jour=("aujourd'hui" if times[i].date()==now.date()
                  else ("demain" if times[i].date()==(now+datetime.timedelta(days=1)).date() else fr_jour(times[i].date())))
            bascule=dict(to=other, jour=jour, heure=times[i].strftime("%Hh"), dir=dir8(dd)); break

    # --- consensus J+2..J+4 (modeles globaux) ---
    longmodels=["ecmwf_ifs025","icon_eu","gfs_seamless"]
    def cross_long(var,i):
        out=[]
        for m in longmodels:
            s=series(H,var,m)
            if s and i<len(s) and s[i] is not None: out.append(s[i])
        return out
    consensus=[]
    for dd in range(2,5):
        day=(now+datetime.timedelta(days=dd)).date()
        idx=[i for i in range(n) if times[i].date()==day and 8<=times[i].hour<=18]
        if not idx: continue
        vmins=[];vmaxs=[];gusts=[];dirs=[];spreads2=[]
        for i in idx:
            v=cross_long("wind_speed_10m",i)
            if v: vmins.append(min(v)); vmaxs.append(max(v)); spreads2.append(max(v)-min(v))
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
        cf="Élevée" if sp<5 else ("Modérée" if sp<10 else "Faible")
        consensus.append(dict(day=fr_jour(day), wdir=dir8(avg(dirs)) if dirs else "?",
            vmin=vmin, vmax=vmax, force=force, gust=round(max(gusts)) if gusts else None,
            houle_dir=hdir, houle=("%.1f m"%mer).replace(".",",") if mer is not None else "n/d", conf=cf))
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

    # estimation BMS : Meteo-France emet un BMS Cote des force 7 (28 kn soutenu) ;
    # les rafales 34-40 kn = coup de vent. On declenche sur les rafales ET le vent max (pas la moyenne lissee).
    bms_est = ("coup de vent" if (raf_max >= 40 or vent_max_moy >= 34)
               else ("grand frais à coup de vent" if (raf_max >= 34 or vent_max_moy >= 28) else None))

    brief=dict(
        generated=fr_date(now),
        bms_est=bms_est,
        i_now=i_now, n=n,
        chart=chart, detail=detail,
        nav=dict(color=fc_color, status=nav_status, reason=nav_reason),
        confiance=conf, dom_dir=dom_dir,
        vent_max=round(vent_max_moy), raf_max=round(raf_max), mer_max=round(mer_max,1),
        cape_max=round(cape_max), cs_gust=round(cs_gust),
        p_raf30_tom=p_raf30_tom,
        mouillages=moor, mouillage_best=best, mouillage_bascule=bascule,
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

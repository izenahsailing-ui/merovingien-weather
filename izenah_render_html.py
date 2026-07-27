# -*- coding: utf-8 -*-
"""IZENAH - rendu HTML interactif du briefing.

Reprend fidelement la mise en page du PDF v7 (memes blocs, meme ordre, memes
couleurs) et remplace la contrainte de page par des sections depliables :
plus aucun texte tronque, et le detail est disponible sans encombrer.

Usage : render_html(brief, "Briefing_Izenah.html")
"""
import json, html, math

# ---------------- Palette (reprise du PDF) ----------------
NAVY   = "#133A5C"
NAVY2  = "#1B4E73"
NIGHT  = "#17314A"
GOLD   = "#C99A2E"
GREEN  = "#1E7A4C"
AMBER  = "#B5740F"
RED    = "#C02718"
GREY   = "#5C6B7A"
INK    = "#1B2B38"
INK2   = "#4A5C6B"
LINE   = "#D9E1E8"
LIGHT  = "#F4F6F8"
BLUE   = "#1B6FA8"
TEAL   = "#178E92"
BG_G   = "#E3F1E7"
BG_A   = "#FBEEDA"
BG_R   = "#F8DFDB"

COL = {"G": GREEN, "A": AMBER, "R": RED, "X": GREY}
BGC = {"G": BG_G, "A": BG_A, "R": BG_R, "X": "#EDF1F4"}

DEG = {"N":0,"NE":45,"E":90,"SE":135,"S":180,"SW":225,"W":270,"NW":315,"?":None}

def e(s):
    return html.escape(str(s if s is not None else ""))

def vcol(frac):
    return GREEN if frac < 0.35 else (AMBER if frac < 0.60 else RED)

def wind_col(kn):
    return GREEN if kn <= 14 else (AMBER if kn <= 22 else RED)

def gust_col(kn):
    if kn is None: return GREY
    return GREEN if kn <= 20 else (AMBER if kn <= 30 else RED)

def sea_col(h):
    if h is None: return GREY
    return GREEN if h <= 0.5 else (AMBER if h <= 1.25 else RED)

def arrow(card, color=BLUE, size=15):
    """Fleche vectorielle : pointe vers ou VA le flux (comme le PDF)."""
    d = DEG.get(card)
    if d is None:
        return '<span style="color:%s">n/d</span>' % GREY
    return ('<svg width="%d" height="%d" viewBox="0 0 24 24" style="vertical-align:middle">'
            '<g transform="rotate(%d 12 12)">'
            '<line x1="12" y1="20" x2="12" y2="5" stroke="%s" stroke-width="2.6" stroke-linecap="round"/>'
            '<polyline points="7,10 12,4.5 17,10" fill="none" stroke="%s" stroke-width="2.6" '
            'stroke-linecap="round" stroke-linejoin="round"/></g></svg>'
            % (size, size, (d + 180) % 360, color, color))

def icon_ciel(k):
    if k == "moon":
        return ('<svg width="15" height="15" viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" '
                'fill="#3D5A73"/></svg>')
    if k == "sun":
        return ('<svg width="15" height="15" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.6" fill="%s"/>'
                '<g stroke="%s" stroke-width="1.8" stroke-linecap="round">'
                '<line x1="12" y1="1.5" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22.5"/>'
                '<line x1="1.5" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22.5" y2="12"/>'
                '<line x1="4.6" y1="4.6" x2="6.4" y2="6.4"/><line x1="17.6" y1="17.6" x2="19.4" y2="19.4"/>'
                '<line x1="19.4" y1="4.6" x2="17.6" y2="6.4"/><line x1="6.4" y1="17.6" x2="4.6" y2="19.4"/></g></svg>'
                % (GOLD, GOLD))
    return ('<svg width="15" height="15" viewBox="0 0 24 24"><path d="M6 18h11a4 4 0 0 0 .4-8A6 6 0 0 0 6 11a3.5 3.5 0 0 0 0 7z" '
            'fill="#93A7B6"/></svg>')

# ---------------- Graphe vent heure par heure (SVG) ----------------
def chart_svg(ch):
    hours = ch.get("hours", [])
    if not hours:
        return '<div class="nodata">Données horaires indisponibles.</div>'
    n = len(hours)
    W, H = 1000, 250
    L, R, T, B = 44, 52, 16, 30
    aw, ah = W - L - R, H - T - B
    ymax = max(40, (max(ch["gust"] + ch["mx"]) // 10 + 1) * 10)
    X = lambda i: L + aw * i / max(1, n - 1)
    Y = lambda v: T + ah * (1 - min(v, ymax) / ymax)
    s = ['<svg viewBox="0 0 %d %d" class="chart">' % (W, H)]
    # bandes de seuil (valables pour le VENT MOYEN)
    for lo, hi, c in ((0, 14, BG_G), (14, 22, BG_A), (22, ymax, BG_R)):
        s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" opacity=".55"/>'
                 % (L, Y(hi), aw, Y(lo) - Y(hi), c))
    # nuit
    i = 0
    while i < n:
        if ch["night"][i]:
            j = i
            while j + 1 < n and ch["night"][j + 1]:
                j += 1
            s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#8FA3B3" opacity=".22"/>'
                     % (X(i), T, max(2, X(j) - X(i)), ah))
            i = j + 1
        else:
            i += 1
    # quadrillage horaire
    for i in range(n):
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#FFFFFF" stroke-width=".8" opacity=".55"/>'
                 % (X(i), T, X(i), T + ah))
    # echelle gauche + Beaufort droite
    for v in range(0, int(ymax) + 1, 10):
        s.append('<text x="%.1f" y="%.1f" class="ax">%d</text>' % (L - 8, Y(v) + 4, v))
    for kn, lab in ((3,"force 3"),(10,"force 4"),(16,"force 5"),(21,"force 6"),(27,"force 7"),(33,"force 8")):
        if kn <= ymax:
            s.append('<text x="%.1f" y="%.1f" class="bf">%s</text>' % (W - R + 6, Y(kn) + 3, lab))
    # plage min-max
    pts = " ".join("%.1f,%.1f" % (X(i), Y(ch["mx"][i])) for i in range(n))
    pts += " " + " ".join("%.1f,%.1f" % (X(i), Y(ch["mn"][i])) for i in range(n - 1, -1, -1))
    s.append('<polygon points="%s" fill="%s" opacity=".22"/>' % (pts, BLUE))
    # rafales
    s.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2" stroke-dasharray="5 4"/>'
             % (" ".join("%.1f,%.1f" % (X(i), Y(ch["gust"][i])) for i in range(n)), GOLD))
    # moyen
    s.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.6" stroke-linejoin="round"/>'
             % (" ".join("%.1f,%.1f" % (X(i), Y(ch["mean"][i])) for i in range(n)), BLUE))
    for i in range(n):
        s.append('<circle cx="%.1f" cy="%.1f" r="2.4" fill="%s"/>' % (X(i), Y(ch["mean"][i]), BLUE))
    # heures
    for i in range(0, n, 2):
        s.append('<text x="%.1f" y="%.1f" class="hx">%s</text>' % (X(i), H - 10, e(hours[i])))
    s.append('</svg>')
    # fleches de direction au-dessus, alignees sur la grille
    ar = ['<div class="arrows">']
    for i in range(0, n, max(1, n // 12)):
        ar.append('<span style="left:%.2f%%">%s</span>'
                  % (100.0 * (L + aw * i / max(1, n - 1)) / W, arrow(ch["dir"][i], BLUE, 14)))
    ar.append('</div>')
    return "".join(ar) + "".join(s)

# ---------------- Blocs ----------------
def bloc_alertes(b):
    bo = b.get("bms_officiel")
    if bo and bo.get("actif_zone"):
        g = {"k": "R", "t": "BMS OFFICIEL EN COURS",
             "s": bo.get("avis") or "Bulletin météo spécial Météo-France sur la zone",
             "long": bo.get("zone_texte") or ""}
    elif bo is None:
        g = {"k": "X", "t": "BULLETIN OFFICIEL NON VÉRIFIÉ",
             "s": "Le bulletin Météo-France n'a pas pu être consulté. Son absence n'est pas un feu vert.", "long": ""}
    else:
        g = {"k": "G", "t": "PAS DE BMS EN COURS",
             "s": "Bulletin officiel Météo-France vérifié à la génération", "long": ""}
    p30 = b.get("p_raf30_tom")
    raf = b.get("raf_max") or 0
    if b.get("bms_est"):
        d = {"k": "R", "t": "BMS PROBABLE : %s" % b["bms_est"].upper(),
             "s": "Rafales jusqu'à %d nœuds attendues" % raf, "long": ""}
    elif raf >= 30 or (p30 or 0) >= 20:
        d = {"k": "A", "t": "ÉPISODE SIGNALÉ",
             "s": "Rafales %d nœuds · risque de dépasser 30 nœuds : %d%%" % (raf, p30 or 0), "long": ""}
    else:
        d = {"k": "G", "t": "PAS D'ÉPISODE MAJEUR",
             "s": "Aucun coup de vent notable prévu" + (" · risque de dépasser 30 nœuds : %d%%" % p30 if p30 is not None else ""),
             "long": ""}
    out = ['<div class="grid2 gap">']
    for c in (g, d):
        icon = "✓" if c["k"] == "G" else ("!" if c["k"] in ("A", "R") else "?")
        out.append('<div class="alert" style="background:%s"><div class="ic">%s</div>'
                   '<div><div class="t">%s</div><div class="s">%s</div>%s</div></div>'
                   % (COL[c["k"]], icon, e(c["t"]), e(c["s"]),
                      ('<details class="inline"><summary>texte intégral du bulletin</summary><p>%s</p></details>'
                       % e(c["long"])) if c["long"] else ""))
    out.append("</div>")
    return "".join(out)

def bloc_badges(b):
    nav, k = b["nav"], b["nav"]["color"]
    conf, cp = b.get("confiance", ""), b.get("confiance_pct", 0)
    ck = "G" if cp >= 70 else ("A" if cp >= 50 else "R")
    return """
<div class="grid2 gap">
  <div class="panel" style="border-left-color:%s">
    <div class="ph">NAVIGATION : PEUX-TU SORTIR ?</div>
    <div class="pv" style="color:%s"><span class="dot" style="background:%s"></span>%s</div>
    <div class="pr">%s</div>
    <div class="lg"><span><i style="background:%s"></i>favorable</span><span><i style="background:%s"></i>prudence</span><span><i style="background:%s"></i>déconseillé</span></div>
  </div>
  <div class="panel" style="border-left-color:%s">
    <div class="ph">FIABILITÉ : PRÉVISION SÛRE ?</div>
    <div class="pv" style="color:%s"><span class="dot" style="background:%s"></span>%s · %d%%</div>
    <div class="pr">%s</div>
    <div class="lg"><span><i style="background:%s"></i>faible</span><span><i style="background:%s"></i>modérée</span><span><i style="background:%s"></i>élevée</span></div>
  </div>
</div>""" % (COL[k], COL[k], COL[k], e(nav["status"]), e(nav["reason"]),
             GREEN, AMBER, RED,
             COL[ck], COL[ck], COL[ck], e(conf), cp, e(b.get("conf_detail", "")),
             RED, AMBER, GREEN)

def bloc_mouillages(b):
    """Les cartes lisent la MEME source que la ligne « Où dormir » : le confort
    de la nuit qui vient. C'est ce qui supprime la contradiction du PDF, ou la
    carte annoncait « Tres confortable » quand la ligne du dessous disait « a eviter »."""
    nu = b.get("nuits", [])
    per = nu[0]["per"] if nu else {}
    out = ['<h3><i></i>Tes deux mouillages<em>confort de la nuit qui vient</em></h3>', '<div class="grid2 gap">']
    for m in b.get("mouillages", []):
        f = per.get(m["name"], m["frac"])
        m = dict(m, verdict=("Très confortable" if f < 0.35 else
                             ("Correct" if f < 0.60 else
                              ("Inconfortable" if f < 0.78 else "À éviter"))))
        out.append("""<div class="moor">
  <div class="mh"><b>%s</b><span style="color:%s">%s</span></div>
  <div class="gauge"><div class="bar"></div><div class="cur" style="left:%.1f%%;border-color:%s"></div></div>
  <div class="gl"><span>Confort</span><span>Risque</span></div>
  <div class="mx">Exposition calculée dans le lit du vent dominant : <b>%.2f</b> sur 1</div>
</div>""" % (e(m["name"]), vcol(f), e(m["verdict"]), min(97, max(3, f * 100)), vcol(f), m.get("expo_dir", 0)))
    out.append("</div>")
    nu = b.get("nuits", [])
    if nu:
        parts = []
        for x in nu:
            parts.append('<b>%s</b> : %s (<span style="color:%s">%s</span>) ou %s (<span style="color:%s">%s</span>)'
                         % (e(x["label"]), e(x["best"]), vcol(x["frac"]), e(x["verdict"].lower()),
                            e(x["alt"]), vcol(x["alt_frac"]), e(x["alt_verdict"].lower())))
        out.append('<p class="where">Où dormir : ' + " · ".join(parts) + "</p>")
    return "".join(out)

def bloc_reco(b):
    nu = b.get("nuits", [])
    soir = ("Mouille à <b>%s</b> : %s cette nuit, contre %s à %s."
            % (e(nu[0]["best"]), e(nu[0]["verdict"].lower()), e(nu[0]["alt_verdict"].lower()), e(nu[0]["alt"]))) if nu else "—"
    dem = "%s Vent %s, jusqu'à %d nœuds, rafales %d. Mer %s m." % (
        {"G": "Belle fenêtre.", "A": "Conditions à surveiller.", "R": "Sortie déconseillée."}[b["nav"]["color"]],
        e(b.get("dom_dir", "")), b.get("vent_max", 0), b.get("raf_max", 0),
        str(b.get("mer_max", 0)).replace(".", ","))
    ten = " · ".join("%s : %d%%" % (e(t[0]), round(t[1] * 100)) for t in b.get("tendance", [])) or "—"
    return """
<div class="reco">
  <div class="rt">RECOMMANDATION ET ANTICIPATION</div>
  <div class="rl"><span class="pill">CE SOIR</span><div>%s</div></div>
  <div class="rl"><span class="pill">DEMAIN</span><div>%s</div></div>
  <div class="rl"><span class="pill">ANTICIPE</span><div>%s</div></div>
</div>""" % (soir, dem, ten)

def bloc_detail(b):
    rows = []
    for d in b.get("detail", []):
        cls = ' class="nuit"' if d.get("night") else ""
        mer = d.get("mer")
        rows.append("""<tr%s>
<td class="hh">%s %s</td>
<td class="w">%s <b style="color:%s">%d à %d nds</b><span>%s %s</span></td>
<td style="color:%s"><b>%s</b></td>
<td>%s %s</td>
<td style="color:%s"><b>%s</b></td>
<td>%s / %s°C</td>
<td>%s %s</td>
<td>%s hPa</td></tr>""" % (
            cls, icon_ciel(d.get("ciel")), e(d["hh"]),
            arrow(d["wdir"], "#7FB3D8" if d.get("night") else BLUE),
            wind_col(d["vmax"]), d["vmin"], d["vmax"], e(d["wdir"]), e(d.get("force", "")),
            gust_col(d.get("gust")), e(d.get("gust", "n/d")),
            arrow(d.get("houle_dir", "?"), TEAL), e(d.get("houle_p") or "n/d"),
            sea_col(mer), (("%.1f m" % mer).replace(".", ",")) if mer is not None else "n/d",
            e(d.get("air", "n/d")), e(d.get("eau", "n/d")),
            icon_ciel(d.get("ciel")), e(d.get("ciel_lbl", "")),
            e(d.get("press", "n/d"))))
    return """
<h3><i></i>Le détail des conditions<em>cadence 2 heures, valeurs colorées selon les seuils</em></h3>
<div class="tw"><table class="det">
<tr><th>Heure</th><th>Vent</th><th>Rafales<br><small>nœuds</small></th><th>Houle<br><small>d'où, période</small></th>
<th>Mer<br><small>hauteur</small></th><th>Air / Eau</th><th>Ciel</th><th>Pression</th></tr>
%s
</table></div>""" % "".join(rows)

def bloc_jours(b):
    rows = []
    for c in b.get("consensus", []):
        k = c.get("nav", "G")
        rows.append("""<tr>
<td>%s</td><td><span class="bul" style="background:%s"></span><b>%s</b></td>
<td style="color:%s"><b>%d à %d nds</b><span class="sub">%s</span></td>
<td style="color:%s"><b>%s nds</b></td>
<td>%s %s</td>
<td><span class="cf" style="background:%s">%s</span></td></tr>""" % (
            arrow(c.get("wdir", "?")), COL[k], e(c["day"]),
            wind_col(c["vmax"]), c["vmin"], c["vmax"], e(c.get("force", "")),
            gust_col(c.get("gust")), e(c.get("gust", "n/d")),
            arrow(c.get("houle_dir", "?"), TEAL), e(c.get("houle", "n/d")),
            COL["G" if c["conf_pct"] >= 70 else ("A" if c["conf_pct"] >= 50 else "R")], e(c.get("conf", ""))))
    return """
<h3><i></i>Les prochains jours<em>consensus des modèles, J+2 à J+5 · pastille = feu navigation</em></h3>
<div class="tw"><table class="det jours">
<tr><th>Dir.</th><th>Jour</th><th>Vent</th><th>Rafales</th><th>Houle</th><th>Fiabilité</th></tr>
%s
</table></div>""" % "".join(rows)

def bloc_tendance(b):
    rows = []
    for label, frac in b.get("tendance", []):
        pct = round(frac * 100)
        c = GREEN if frac < 0.2 else (AMBER if frac < 0.5 else RED)
        w = frac * 100  # pas de largeur plancher : 0% doit se voir comme 0
        inside = w >= 22
        rows.append("""<div class="tr">
  <div class="tl">%s</div>
  <div class="tbar"><div class="tfill" style="width:%.1f%%;background:%s"></div>
  <span class="tv" style="%s">%d %%</span></div></div>"""
                    % (e(label), w, c,
                       ("left:8px;color:#fff") if inside else ("left:%.1f%%;color:%s" % (w + 1.2, INK2)), pct))
    return """
<h3><i></i>La tendance à douze jours<em>ensembles, part des scénarios franchissant le seuil</em></h3>
%s""" % "".join(rows)

def bloc_attention(b):
    li = [("Demain", "%s. %s" % (e(b["nav"]["status"].lower()).capitalize(), e(b["nav"]["reason"]))),
          ("Situation", e(b.get("contexte", ""))),
          ("Mer", "%s m" % str(b.get("mer_max", 0)).replace(".", ",")),
          ("Orage et grain", "risque %s" % e(b.get("orage", "")))]
    nu = b.get("nuits", [])
    if nu:
        li.insert(2, ("Mouillage", "%s cette nuit (%s)" % (e(nu[0]["best"]), e(nu[0]["verdict"].lower()))))
    return ('<div class="att"><div class="at">CE QUI MÉRITE ATTENTION</div><ul>'
            + "".join("<li><b>%s :</b> %s</li>" % (a, c) for a, c in li) + "</ul></div>")

# ---------------- Page ----------------
CSS = """
*{box-sizing:border-box}
body{margin:0;background:#EAEFF3;min-width:794px;color:INK;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
 font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased}
.page{width:794px;margin:0 auto;background:#fff;padding:0 0 34px;box-shadow:0 2px 18px rgba(15,40,60,.10)}
.inner{padding:0 22px}
.hd{background:NAVY;color:#fff;padding:16px 22px;display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap}
.hd h1{margin:0;font-size:23px;letter-spacing:.4px;font-weight:800}
.hd h1 em{color:GOLD;font-style:normal}
.hd .z{font-size:12.5px;opacity:.85;margin-top:3px}
.hd .r{margin-left:auto;text-align:right;font-size:13px;font-weight:700}
.hd .r em{display:block;font-style:italic;font-weight:400;font-size:11.5px;color:GOLD;opacity:.95}
.rule{height:3px;background:GOLD}
.grid2{display:grid;grid-template-columns:1fr 1fr}
.gap{gap:12px}

.alert{border-radius:9px;padding:12px 14px;color:#fff;display:flex;gap:11px;align-items:flex-start}
.alert .ic{width:26px;height:26px;border-radius:50%;background:rgba(255,255,255,.22);display:flex;
 align-items:center;justify-content:center;font-weight:800;flex:0 0 auto}
.alert .t{font-weight:800;font-size:13.5px;letter-spacing:.3px}
.alert .s{font-size:12.5px;opacity:.95;margin-top:2px}
.panel{background:LIGHT;border:1px solid LINE;border-left:5px solid;border-radius:9px;padding:11px 14px}
.panel .ph{font-size:11px;letter-spacing:.9px;font-weight:800;color:INK2}
.panel .pv{font-size:21px;font-weight:800;margin:3px 0 2px;display:flex;align-items:center;gap:8px}
.panel .dot{width:12px;height:12px;border-radius:50%;display:inline-block}
.panel .pr{font-size:12.5px;color:INK2}
.lg{margin-top:5px;font-size:11px;color:INK2;display:flex;gap:12px}
.lg i{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:4px}
h3{font-size:16px;margin:22px 0 9px;display:flex;align-items:center;gap:9px;font-weight:800}
h3 i{width:5px;height:17px;background:GOLD;border-radius:2px;display:inline-block}
h3 em{margin-left:auto;font-style:italic;font-weight:400;font-size:11.5px;color:INK2}
.moor{background:LIGHT;border:1px solid LINE;border-radius:9px;padding:11px 14px}
.moor .mh{display:flex;justify-content:space-between;font-size:15px;font-weight:800;margin-bottom:8px}
.gauge{position:relative;height:11px}
.gauge .bar{height:11px;border-radius:6px;background:linear-gradient(90deg,BG_G 0%,BG_G 35%,BG_A 35%,BG_A 60%,BG_R 60%,BG_R 100%)}
.gauge .cur{position:absolute;top:-3px;width:15px;height:15px;border-radius:50%;background:#fff;border:4px solid;transform:translateX(-50%)}
.gl{display:flex;justify-content:space-between;font-size:10.5px;color:INK2;margin-top:3px}
.mx{font-size:11.5px;color:INK2;margin-top:6px}
.where{background:LIGHT;border:1px solid LINE;border-radius:9px;padding:9px 13px;font-size:12.5px;margin:11px 0 0}
.reco{background:NAVY2;color:#fff;border-radius:9px;padding:12px 15px;margin:14px 0 0}
.reco .rt{font-size:11.5px;letter-spacing:.9px;font-weight:800;margin-bottom:8px}
.reco .rl{display:flex;gap:12px;align-items:flex-start;margin:6px 0;font-size:13px}
.reco .pill{background:GOLD;color:NAVY;font-size:10.5px;font-weight:800;letter-spacing:.6px;padding:3px 9px;
 border-radius:4px;flex:0 0 82px;text-align:center;margin-top:1px}
.tw{}
table.det{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
table.det th{background:NAVY2;color:#fff;text-align:left;padding:7px 9px;font-size:11px;letter-spacing:.4px;font-weight:700}
table.det th small{font-weight:400;opacity:.8;font-size:9.5px}
table.det td{padding:7px 9px;border-bottom:1px solid #EDF1F4}
table.det tr:nth-child(even) td{background:#F8FAFB}
table.det tr.nuit td{background:NIGHT;color:#D7E3EC;border-bottom-color:#22405A}
table.det tr.nuit td b{color:#fff}
td.hh{white-space:nowrap;font-weight:700}
td.w b{display:inline-block} td.w span{display:block;font-size:10.5px;color:INK2;margin-left:20px}
table.det span.sub{display:block;font-size:10.5px;color:INK2;font-weight:400}
tr.nuit td.w span{color:#9DB4C6}
.bul{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:7px}
.cf{color:#fff;font-size:11px;font-weight:700;padding:3px 11px;border-radius:5px;display:inline-block}
.chart{width:100%;height:auto;display:block}
.chart .ax{font-size:11px;fill:INK2;text-anchor:end}
.chart .bf{font-size:10px;fill:#8FA3B3}
.chart .hx{font-size:10.5px;fill:INK2;text-anchor:middle}
.arrows{position:relative;height:20px}
.arrows span{position:absolute;transform:translateX(-50%)}
.clg{font-size:11.5px;color:INK2;margin-top:5px}
.tr{margin:9px 0}
.tl{font-size:12.5px;margin-bottom:3px}
.tbar{position:relative;height:19px;background:#EDF1F4;border-radius:10px;overflow:hidden}
.tfill{height:19px;border-radius:10px}
.tv{position:absolute;top:2px;font-size:11.5px;font-weight:700}
.att{background:LIGHT;border:1px solid LINE;border-left:4px solid GOLD;border-radius:9px;padding:12px 16px;margin-top:20px}
.att .at{font-weight:800;font-size:13px;letter-spacing:.5px;margin-bottom:6px}
.att ul{margin:0;padding-left:17px} .att li{font-size:12.5px;margin:3px 0}
details{border:1px solid LINE;border-radius:9px;margin:11px 0;background:#fff}
details summary{cursor:pointer;padding:10px 14px;font-size:12.5px;font-weight:700;color:BLUE;list-style:none;
 display:flex;align-items:center;gap:8px;user-select:none}
details summary::-webkit-details-marker{display:none}
details summary:before{content:"+";display:inline-flex;width:18px;height:18px;border-radius:50%;background:BLUE;
 color:#fff;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex:0 0 auto}
details[open] summary:before{content:"−"}
details .dc{padding:0 14px 13px;font-size:12.8px;color:INK2}
details .dc p{margin:7px 0}
details.inline{border:none;background:transparent;margin:5px 0 0}
details.inline summary{padding:0;color:#fff;font-size:11.5px;opacity:.95}
details.inline summary:before{background:rgba(255,255,255,.25);width:15px;height:15px;font-size:12px}
details.inline p{color:#fff;font-size:12px;margin:6px 0 0;opacity:.95}
.nodata{background:LIGHT;border:1px dashed LINE;border-radius:9px;padding:22px;text-align:center;color:INK2}
.ft{font-size:11px;color:INK2;margin-top:20px;border-top:1px solid LINE;padding-top:11px}
.sum{background:LIGHT;border:1px solid LINE;border-radius:9px;padding:11px 14px;margin:14px 0 0;font-size:13px}
"""

def build_css():
    c = CSS
    for k, v in (("NAVY2", NAVY2), ("NAVY", NAVY), ("NIGHT", NIGHT), ("GOLD", GOLD), ("LIGHT", LIGHT),
                 ("LINE", LINE), ("INK2", INK2), ("INK", INK), ("BLUE", BLUE),
                 ("BG_G", BG_G), ("BG_A", BG_A), ("BG_R", BG_R)):
        c = c.replace(k, v)
    return c

def render_html(b, path="Briefing_Izenah.html"):
    zone = "La Ciotat · Bandol · Sanary · Les Embiez"
    doc = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=794">
<title>Briefing marine Izenah</title><style>%s</style></head><body>
<div class="page">
  <div class="hd">
    <div><h1>BRIEFING MARINE <em>IZENAH</em></h1><div class="z">%s &nbsp;|&nbsp; au mouillage, 24h</div></div>
    <div class="r">%s<em>briefing automatique · données réelles</em></div>
  </div>
  <div class="rule"></div>
  <div class="inner">
    <div style="height:14px"></div>
    %s
    <div style="height:12px"></div>
    %s
    <details><summary>Pourquoi ce feu, et comment la fiabilité est calculée</summary><div class="dc">
      <p><b>Le feu Navigation</b> retient le scénario haut crédible, jamais la moyenne des modèles : sur une sortie côtière, une moyenne lisse justement l'épisode qui te met dedans.</p>
      <p><b>La fiabilité</b> croise trois choses : l'accord entre les modèles, la dispersion des scénarios d'ensemble, et la stabilité d'un run à l'autre. %s</p>
      <p><b>Situation :</b> %s</p>
    </div></details>
    %s
    %s
    %s
    <details><summary>Comment le confort au mouillage est calculé</summary><div class="dc">
      <p>Le bateau s'aligne sur le vent. Ce qui compte n'est donc pas la direction de la houle par rapport au nord, mais son <b>écart avec le vent</b> : de face tu tangues, de travers tu roules.</p>
      <p>La <b>période</b> compte autant que la hauteur. Izenah III roule sur environ 3 secondes : un clapot court de 40 cm gêne davantage qu'une houle longue d'un mètre.</p>
      <p>Sous 5 nœuds, le bateau ne tient plus son cap et se met en travers : <b>moins de vent ne veut pas dire meilleure nuit</b>.</p>
    </div></details>
    %s
    <p class="sum"><b>Vent dominant</b> de %s, jusqu'à %d nœuds, rafales %d. <b>Orage et grain :</b> risque <b style="color:%s">%s</b>.</p>

    <h3><i></i>Le vent heure par heure<em>La Ciotat · maille fine 1,3 km</em></h3>
    %s
    <p class="clg">La plage bleutée montre le vent mini et maxi entre modèles : plus elle est étroite, plus c'est fiable. Zone grisée = la nuit. Échelle de droite = la force Beaufort. Les bandes de couleur valent pour le <b>vent moyen</b>, pas pour les rafales.</p>
    %s
    %s
    %s
    <details><summary>Méthode et sources</summary><div class="dc">
      <p>5 modèles confrontés et pondérés (maille fine 1,3 km, ARPEGE, ECMWF, ICON, GFS) plus les ensembles probabilistes. Le badge Navigation retient le scénario haut crédible, jamais la moyenne. Le bulletin officiel et la vigilance Météo-France font foi en cas de divergence.</p>
      <p>Flèches : bleu = vent, turquoise = houle. Elles pointent vers où va le flux.</p>
      <p>Généré le %s.</p>
    </div></details>
    <div class="ft">Le Mérovingien · briefing automatique · le bulletin officiel Météo-France fait foi.</div>
  </div>
</div></body></html>""" % (
        build_css(), e(zone), e(b.get("generated", "")),
        bloc_alertes(b), bloc_badges(b), e(b.get("conf_detail", "")), e(b.get("contexte", "")),
        bloc_mouillages(b), bloc_reco(b),
        "", bloc_detail(b),
        e(b.get("dom_dir", "")), b.get("vent_max", 0), b.get("raf_max", 0),
        {"faible": GREEN, "modéré": AMBER, "élevé": RED}.get(b.get("orage", ""), GREY), e(b.get("orage", "")),
        chart_svg(b.get("chart", {})),
        bloc_jours(b), bloc_tendance(b), bloc_attention(b),
        e(b.get("generated", "")))
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path

if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "archives/brief_pour_2026-07-04.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "Briefing_Izenah.html"
    with open(src, encoding="utf-8") as f:
        b = json.load(f)
    print(render_html(b, out))

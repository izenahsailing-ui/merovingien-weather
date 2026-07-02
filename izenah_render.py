# -*- coding: utf-8 -*-
"""IZENAH — rendu PDF du briefing (format v6) a partir des donnees reelles.
Consomme build_brief() du moteur et produit le PDF + la synthese Telegram."""
import math
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, Flowable, PageBreak)
from reportlab.pdfbase.pdfmetrics import stringWidth
from izenah_engine import build_brief

NAVY=HexColor("#0A2540");BLUE=HexColor("#15467A");MARINE=HexColor("#1B6CA8")
STEEL=HexColor("#2E6E8E");SLATE=HexColor("#22384E");LIGHT=HexColor("#EEF4F9")
ZEBRA=HexColor("#F4F8FB");GOLD=HexColor("#D6A93B");INK=HexColor("#16202C")
GREY=HexColor("#5C6B7A");LINE=HexColor("#D5DEE7");TEAL=HexColor("#0E9AA7")
WINDN=HexColor("#9FC6E4");TEALN=HexColor("#6FD8E0");CLOUDC=HexColor("#9DB0C0")
GREEN=HexColor("#1C7C54");AMBER=HexColor("#C07A12");RED=HexColor("#B3261E")
CGd,CAd,CRd="#1C7C54","#B5740F","#C02718";CGn,CAn,CRn="#63D58F","#F1B24A","#FF8B79"
def wind_hex(kn,n):c=(CGn,CAn,CRn) if n else (CGd,CAd,CRd);return c[0] if kn<=14 else (c[1] if kn<=22 else c[2])
def gust_hex(kn,n):c=(CGn,CAn,CRn) if n else (CGd,CAd,CRd);return c[0] if kn<=20 else (c[1] if kn<=30 else c[2])
def sea_hex(h,n):
    if h is None: return CGn if n else CGd
    c=(CGn,CAn,CRn) if n else (CGd,CAd,CRd);return c[0] if h<=0.5 else (c[1] if h<=1.25 else c[2])
DIRS={"N":0,"NE":45,"E":90,"SE":135,"S":180,"SW":225,"W":270,"NW":315,"NNW":337.5,"SSE":157.5,"?":315}
ABRI={"La Ciotat":("Mistral, Ouest à Nord","Est et Sud-Est"),
      "La Madrague (St-Cyr)":("Est, Sud-Est, NW (digue)","Sud et Sud-Ouest")}
MF_LINK="https://meteofrance.com/meteo-marine/la-ciotat/570199"

ss=getSampleStyleSheet()
def S(n,**k):return ParagraphStyle(n,parent=ss["Normal"],**k)
sect=S("sect",fontName="Helvetica-Bold",fontSize=10.5,textColor=NAVY,leading=12)
subt=S("subt",fontName="Helvetica-Oblique",fontSize=7.8,textColor=GREY,alignment=2,leading=11)
body=S("body",fontName="Helvetica",fontSize=8.5,textColor=INK,leading=11.4)
small=S("small",fontName="Helvetica",fontSize=7.4,textColor=GREY,leading=9.6)
cH=S("cH",fontName="Helvetica-Bold",fontSize=7.3,textColor=colors.white,alignment=1,leading=9)
cC=S("cC",fontName="Helvetica",fontSize=8,textColor=INK,alignment=1,leading=9.5)
cL=S("cL",fontName="Helvetica",fontSize=8,textColor=INK,alignment=0,leading=9.5)
wC=S("wC",fontName="Helvetica",fontSize=8,textColor=colors.white,alignment=1,leading=9.5)
wL=S("wL",fontName="Helvetica",fontSize=8,textColor=colors.white,alignment=0,leading=9.5)
def colcell(t,hx,a=1,b=True):
    st=S("x",fontName="Helvetica",fontSize=8,textColor=HexColor(hx),alignment=a,leading=9.5)
    return Paragraph(("<b>%s</b>"%t) if b else t,st)
def ventcell(rng,force,hx,night=False):
    fg="#9DB0C0" if night else "#5C6B7A"
    st=S("v",fontName="Helvetica",fontSize=8,alignment=1,leading=8.4)
    return Paragraph("<font color='%s'><b>%s</b></font><br/><font size=6 color='%s'>%s</font>"%(hx,rng,fg,force),st)

def draw_arrow(c,x,y,frm,size,color):
    b=DIRS.get(frm,frm) if isinstance(frm,str) else frm;r=size/2.0;f=r/4.7
    c.saveState();c.translate(x,y);c.rotate(-((b+180)%360));c.setFillColor(color)
    pts=[(0,4.4),(2.0,0.5),(0.65,0.5),(0.65,-4.0),(-0.65,-4.0),(-0.65,0.5),(-2.0,0.5)]
    p=c.beginPath();p.moveTo(pts[0][0]*f,pts[0][1]*f)
    for X,Y in pts[1:]:p.lineTo(X*f,Y*f)
    p.close();c.drawPath(p,fill=1,stroke=0);c.restoreState()
class Arrow(Flowable):
    def __init__(s,frm,size=6*mm,color=MARINE):Flowable.__init__(s);s.frm=frm;s.size=size;s.color=color;s.hAlign="CENTER"
    def wrap(s,*a):return(s.size,s.size)
    def draw(s):draw_arrow(s.canv,s.size/2,s.size/2,s.frm,s.size,s.color)
class WIcon(Flowable):
    def __init__(s,kind,size=5.2*mm,bg=colors.white):Flowable.__init__(s);s.kind=kind;s.size=size;s.bg=bg;s.hAlign="CENTER"
    def wrap(s,*a):return(s.size,s.size)
    def draw(s):
        c=s.canv;r=s.size/2.0;c.saveState();c.translate(r,r);k=s.kind
        def cloud(col,sc=1,dx=0,dy=0):
            c.setFillColor(col)
            for ox,oy,rr in[(-0.38,-0.05,0.42),(0.02,0.22,0.5),(0.44,-0.04,0.4)]:c.circle((ox+dx)*r*sc,(oy+dy)*r*sc,rr*r*sc,fill=1,stroke=0)
            c.roundRect((-0.8+dx)*r*sc,(-0.46+dy)*r*sc,1.52*r*sc,0.55*r*sc,0.18*r*sc,fill=1,stroke=0)
        if k in("sun","moon"):
            if k=="sun":
                c.setFillColor(GOLD);c.setStrokeColor(GOLD);c.setLineWidth(0.8);c.setLineCap(1);c.circle(0,0,r*0.5,fill=1,stroke=0)
                for i in range(8):
                    a=i*math.pi/4;c.line(math.cos(a)*r*0.66,math.sin(a)*r*0.66,math.cos(a)*r*0.98,math.sin(a)*r*0.98)
            else:
                c.setFillColor(HexColor("#F3D272"));c.circle(0,0,r*0.82,fill=1,stroke=0);c.setFillColor(s.bg);c.circle(r*0.34,r*0.2,r*0.74,fill=1,stroke=0)
        elif k=="few":
            c.setFillColor(GOLD);c.setStrokeColor(GOLD);c.setLineWidth(0.7);c.setLineCap(1);c.circle(-r*0.32,r*0.34,r*0.34,fill=1,stroke=0)
            for i in range(8):
                a=i*math.pi/4;c.line(-r*0.32+math.cos(a)*r*0.45,r*0.34+math.sin(a)*r*0.45,-r*0.32+math.cos(a)*r*0.62,r*0.34+math.sin(a)*r*0.62)
            cloud(CLOUDC,0.92,0.18,-0.18)
        elif k=="cloud":cloud(CLOUDC,1)
        c.restoreState()
class AlertStrip(Flowable):
    def __init__(s,width,cards,h=14.5*mm):Flowable.__init__(s);s.width=width;s.cards=cards;s.h=h
    def wrap(s,*a):return(s.width,s.h)
    def _ic(s,c,cx,cy,kind,col):
        c.setFillColor(colors.white);c.circle(cx,cy,3*mm,fill=1,stroke=0)
        if kind=="ok":
            c.setStrokeColor(col);c.setLineWidth(1.4);c.setLineCap(1);c.setLineJoin(1)
            p=c.beginPath();p.moveTo(cx-1.4*mm,cy+0.1*mm);p.lineTo(cx-0.3*mm,cy-1.2*mm);p.lineTo(cx+1.7*mm,cy+1.4*mm);c.drawPath(p,stroke=1,fill=0)
        else:
            c.setFillColor(col);c.roundRect(cx-0.45*mm,cy-0.3*mm,0.9*mm,2.6*mm,0.4*mm,fill=1,stroke=0);c.circle(cx,cy-1.7*mm,0.55*mm,fill=1,stroke=0)
    def draw(s):
        c=s.canv;gap=5*mm;cw=(s.width-gap)/2;h=s.h
        for i,(k,col,t1,t2) in enumerate(s.cards):
            x=i*(cw+gap);c.setFillColor(col);c.roundRect(x,0,cw,h,3*mm,fill=1,stroke=0);s._ic(c,x+8*mm,h/2,k,col)
            maxw=cw-16.5*mm
            c.setFillColor(colors.white);c.setFont("Helvetica-Bold",8.6);c.drawString(x+14.5*mm,h-6*mm,fit_text(t1,"Helvetica-Bold",8.6,maxw))
            c.setFont("Helvetica",7.2);c.drawString(x+14.5*mm,4.0*mm,fit_text(t2,"Helvetica",7.2,maxw))
class StatusPanel(Flowable):
    def __init__(s,width,kind,status,col,reason,legend,h=22*mm):
        Flowable.__init__(s);s.width=width;s.kind=kind;s.status=status;s.col=col;s.reason=reason;s.legend=legend;s.h=h
    def wrap(s,*a):return(s.width,s.h)
    def draw(s):
        c=s.canv;W=s.width;H=s.h
        c.setFillColor(HexColor("#F7FAFC"));c.setStrokeColor(LINE);c.setLineWidth(0.7);c.roundRect(0,0,W,H,4*mm,fill=1,stroke=1)
        c.setFillColor(s.col);c.rect(0,3*mm,2.6*mm,H-6*mm,fill=1,stroke=0)
        c.setFillColor(GREY);c.setFont("Helvetica-Bold",7.3);c.drawString(8*mm,H-6*mm,fit_text(s.kind.upper(),"Helvetica-Bold",7.3,W-14*mm))
        cy=H-12*mm;c.setFillColor(s.col);c.circle(10*mm,cy+0.6*mm,2.3*mm,fill=1,stroke=0)
        fs=12.5
        while fs>8 and stringWidth(s.status,"Helvetica-Bold",fs)>W-18*mm: fs-=0.5
        c.setFont("Helvetica-Bold",fs);c.drawString(14.3*mm,cy-1.4*mm,fit_text(s.status,"Helvetica-Bold",fs,W-18*mm))
        c.setFillColor(GREY);c.setFont("Helvetica",7.3);c.drawString(8*mm,H-17*mm,fit_text(s.reason,"Helvetica",7.3,W-12*mm))
        c.setFont("Helvetica",6.7);lx=8*mm
        for txt,cc in s.legend:
            c.setFillColor(HexColor(cc));c.circle(lx+1*mm,2.6*mm,1*mm,fill=1,stroke=0)
            c.setFillColor(GREY);c.drawString(lx+2.6*mm,1.8*mm,txt);lx+=2.6*mm+stringWidth(txt,"Helvetica",6.7)+3.2*mm
class ComfortGauge(Flowable):
    def __init__(s,width,frac):Flowable.__init__(s);s.width=width;s.frac=frac;s.h=12*mm
    def wrap(s,*a):return(s.width,s.h)
    def draw(s):
        c=s.canv;Wt=s.width;bh=4.6*mm;by=4.4*mm;r=bh/2
        c.setFillColor(HexColor("#BFE3CF"));c.roundRect(0,by,Wt,bh,r,fill=1,stroke=0)
        c.setFillColor(HexColor("#F0D9A6"));c.rect(0.45*Wt,by,0.27*Wt,bh,fill=1,stroke=0)
        c.setFillColor(HexColor("#F1C4BE"));c.roundRect(0.72*Wt,by,0.28*Wt,bh,r,fill=1,stroke=0)
        c.setStrokeColor(LINE);c.setLineWidth(0.5);c.roundRect(0,by,Wt,bh,r,fill=0,stroke=1)
        cx=s.frac*Wt;col=GREEN if s.frac<0.45 else(AMBER if s.frac<0.72 else RED)
        c.setStrokeColor(col);c.setLineWidth(1);c.line(cx,by-1.2*mm,cx,by+bh+1.2*mm)
        c.setFillColor(col);c.circle(cx,by+bh/2,2.3*mm,fill=1,stroke=0)
        c.setFillColor(colors.white);c.circle(cx,by+bh/2,0.95*mm,fill=1,stroke=0)
        c.setFillColor(GREY);c.setFont("Helvetica",6);c.drawString(0,by-7,"Confort");c.drawRightString(Wt,by-7,"Risque")
class WindChart(Flowable):
    def __init__(s,width,height,hours,mn,mx,mean,gust,night,dirs):
        Flowable.__init__(s);s.width=width;s.height=height;s.hours=hours;s.mn=mn;s.mx=mx;s.mean=mean;s.gust=gust;s.night=night;s.dirs=dirs
    def wrap(s,*a):return(s.width,s.height)
    def draw(s):
        c=s.canv;W=s.width;H=s.height;L=21;Rr=24;T=24;B=20
        ax0=L;ay0=B;axw=W-L-Rr;ayh=H-T-B;ymax=max(40,(max(s.gust)//10+1)*10) if s.gust else 40;n=len(s.hours)
        def X(i):return ax0+i*(axw/max(1,(n-1)))
        def Y(v):return ay0+(v/ymax)*ayh
        for lo,hi,col in[(0,14,GREEN),(14,22,AMBER),(22,ymax,RED)]:
            c.setFillColor(col);c.setFillAlpha(0.06);c.rect(ax0,Y(lo),axw,Y(hi)-Y(lo),fill=1,stroke=0)
        c.setFillAlpha(1)
        half=axw/max(1,(n-1))/2.0
        c.setFillColor(SLATE);c.setFillAlpha(0.09)
        for i in range(n):
            if s.night[i]: c.rect(X(i)-half,ay0,2*half,ayh,fill=1,stroke=0)
        c.setFillAlpha(1)
        c.setStrokeColor(HexColor("#E6ECF2"));c.setLineWidth(0.4)
        for i in range(n):c.line(X(i),ay0,X(i),ay0+ayh)
        c.setStrokeColor(LINE);c.setLineWidth(0.4);c.setFont("Helvetica",6);c.setFillColor(GREY)
        for v in range(0,int(ymax)+1,10):
            c.line(ax0,Y(v),ax0+axw,Y(v));c.drawRightString(ax0-3,Y(v)-2,str(v))
        for kn,lab in[(8,"force 3"),(13,"force 4"),(19,"force 5"),(24,"force 6"),(31,"force 7"),(37,"force 8")]:
            if kn<ymax: c.setFillColor(HexColor("#9AA7B4"));c.setFont("Helvetica",5.6);c.drawString(ax0+axw+3,Y(kn)-2,lab)
        c.setFillColor(MARINE);c.setFillAlpha(0.20)
        p=c.beginPath();p.moveTo(X(0),Y(s.mn[0]))
        for i in range(n):p.lineTo(X(i),Y(s.mx[i]))
        for i in range(n-1,-1,-1):p.lineTo(X(i),Y(s.mn[i]))
        p.close();c.drawPath(p,fill=1,stroke=0);c.setFillAlpha(1)
        c.setStrokeColor(AMBER);c.setLineWidth(1.4);c.setDash(2.5,2)
        p=c.beginPath();p.moveTo(X(0),Y(s.gust[0]))
        for i in range(n):p.lineTo(X(i),Y(s.gust[i]))
        c.drawPath(p,stroke=1,fill=0);c.setDash()
        c.setStrokeColor(MARINE);c.setLineWidth(2.1)
        p=c.beginPath();p.moveTo(X(0),Y(s.mean[0]))
        for i in range(n):p.lineTo(X(i),Y(s.mean[i]))
        c.drawPath(p,stroke=1,fill=0)
        for i in range(n):c.setFillColor(NAVY);c.circle(X(i),Y(s.mean[i]),1.15,fill=1,stroke=0)
        c.setFillColor(GREY);c.setFont("Helvetica",6)
        for i in range(0,n,2):c.drawCentredString(X(i),ay0-9,s.hours[i])
        for i in range(0,n,3):draw_arrow(c,X(i),H-19,s.dirs[i] if i<len(s.dirs) else "NW",3.6*mm,MARINE)
        c.setFillColor(NAVY);c.setFont("Helvetica-Bold",8);c.drawString(ax0-2,H-10,"Vent heure par heure (nœuds)")
        lx=ax0+axw-92;c.setStrokeColor(MARINE);c.setLineWidth(2);c.line(lx,H-8,lx+11,H-8)
        c.setFillColor(GREY);c.setFont("Helvetica",6.4);c.drawString(lx+14,H-10,"moyen")
        c.setFillColor(MARINE);c.setFillAlpha(0.20);c.rect(lx+34,H-11,11,6,fill=1,stroke=0);c.setFillAlpha(1)
        c.setFillColor(GREY);c.drawString(lx+47,H-10,"plage");c.setStrokeColor(AMBER);c.setDash(2,2);c.line(lx+68,H-8,lx+79,H-8);c.setDash();c.drawString(lx+82,H-10,"rafale")
class ProbBar(Flowable):
    def __init__(s,frac,width,h=5.2*mm,fill=AMBER):Flowable.__init__(s);s.frac=frac;s.width=width;s.h=h;s.fill=fill
    def wrap(s,*a):return(s.width,s.h)
    def draw(s):
        c=s.canv;c.setFillColor(LIGHT);c.roundRect(0,0,s.width,s.h,s.h/2,fill=1,stroke=0)
        w=max(s.h,s.width*s.frac);c.setFillColor(s.fill);c.roundRect(0,0,w,s.h,s.h/2,fill=1,stroke=0)
        c.setFillColor(colors.white);c.setFont("Helvetica-Bold",7.6);c.drawString(6,(s.h-7.6)/2+1,"%d %%"%int(s.frac*100))

NAVCOL={"G":GREEN,"A":AMBER,"R":RED}
CONFCOL={"ÉLEVÉE":GREEN,"MODÉRÉE":AMBER,"FAIBLE":RED}
PILLCOL={"Élevée":GREEN,"Modérée":AMBER,"Faible":RED}
def vcol_of(f):return CGd if f<0.35 else (CAd if f<0.6 else CRd)
def verdict_of(f):return "Très confortable" if f<0.35 else ("Correct" if f<0.6 else ("Inconfortable" if f<0.78 else "À éviter"))

def fit_text(txt, font, size, maxw):
    """Tronque proprement (…) pour tenir dans maxw points — plus de texte hors cadre."""
    if not txt: return ""
    if stringWidth(txt,font,size)<=maxw: return txt
    while txt and stringWidth(txt+"…",font,size)>maxw: txt=txt[:-1]
    return txt+"…"

def p_word(p):
    try: p=int(round(float(p)))
    except: return ""
    if p>=90: return "quasi certain"
    if p>=65: return "très probable"
    if p>=40: return "probable"
    if p>=15: return "possible"
    return "peu probable"

def narrative(b):
    nav=b["nav"];best=b["mouillage_best"];dd=b["dom_dir"]
    JOUR=("AUJOURD'HUI" if b.get("target")=="today" else "DEMAIN")
    jour=("aujourd'hui" if b.get("target")=="today" else "demain")
    jourC=("Aujourd'hui" if b.get("target")=="today" else "Demain")
    vig=b.get("vigilance");bo=b.get("bms_officiel")
    if bo and bo.get("actif_zone"):
        left=("warn",RED,"BMS OFFICIEL : "+bo["avis"].replace("Avis de ","").upper(),
              "%s — jusqu'à %s"%(bo.get("zone_texte") or bo.get("zone_titre",""),bo.get("fin","")))
    elif vig and vig.get("max_color",1)>=3:
        ph=" / ".join("%s %s"%(k,v) for k,v in vig.get("phenos",{}).items() if v in ("orange","rouge")) or vig.get("max_label","")
        left=("warn", RED if vig["max_color"]>=4 else AMBER, "VIGILANCE %s (officiel)"%vig["max_label"].upper(), "Météo-France Var/13 : "+ph)
    elif bo and not bo.get("actif_zone"):
        left=("warn",AMBER,"BMS EN MÉDITERRANÉE (pas ta zone)","%s — reste attentif au bulletin"%bo["avis"])
    elif b.get("bms_est"): left=("warn",AMBER,"BMS PROBABLE : "+b["bms_est"].upper(),"Estimation modèle, confirme le bulletin officiel")
    else: left=("ok",GREEN,"PAS DE BMS EN COURS","Bulletin officiel Météo-France vérifié à la génération")
    p30=("%d%%"%b["p_raf30_tom"]) if b.get("p_raf30_tom") is not None else "n/d"
    if b["raf_max"]>=30: right=("warn",AMBER,"ÉPISODE SIGNALÉ","%s %s, rafales %d nœuds — risque de dépasser 30 nœuds : %s"%(dd,jour,b["raf_max"],p30))
    else: right=("ok",GREEN,"PAS D'ÉPISODE MAJEUR","Aucun coup de vent notable prévu")
    nuits=b.get("nuits") or []
    best_soir=nuits[0]["best"] if nuits else best
    reco=[("CE SOIR","Mouille à <b>%s</b> : le mieux protégé cette nuit (vent et houle résiduelle comprises)."%best_soir)]
    fen=b.get("fenetre")
    if nav["color"]=="R":
        txt="Conditions musclées. Reste au mouillage protégé ou au port ; vent jusqu'à %d kn, rafales %d."%(b["vent_max"],b["raf_max"])
        if fen and fen["kind"] in ("G","A"): txt+=" Seul créneau plus maniable : <b>%s à %s</b>."%(fen["frm"],fen["to"])
        reco.append((JOUR,txt))
    elif nav["color"]=="A":
        txt="Sortie possible avec prudence ; surveille les rafales (%d kn)%s."%(b["raf_max"]," et le Cap Sicié" if b["cs_gust"]>b["raf_max"]+3 else "")
        if fen and fen["kind"]=="G": txt+=" Meilleure fenêtre : <b>%s à %s</b>."%(fen["frm"],fen["to"])
        elif fen and fen["kind"]=="A": txt+=" Créneau le plus sûr : <b>%s à %s</b>."%(fen["frm"],fen["to"])
        reco.append((JOUR,txt))
    else:
        txt="Belle fenêtre : vent modéré, mer maniable, bon créneau pour naviguer."
        if fen and fen["kind"]=="G": txt="Belle journée : vent modéré, mer maniable. Meilleur créneau : <b>%s à %s</b>."%(fen["frm"],fen["to"])
        reco.append((JOUR,txt))
    worst=None
    for c in b["consensus"]:
        if c["gust"] and (worst is None or c["gust"]>worst["gust"]): worst=c
    if worst and worst["gust"] and worst["gust"]>=30: reco.append(("ANTICIPE","%s : %s, rafales jusqu'à %d kn, prévois un abri très protégé."%(worst["day"],worst["force"],worst["gust"])))
    elif b["tendance"]: lab,fr=b["tendance"][0];reco.append(("ANTICIPE","%s : %d%%, garde un œil sur les prochains runs."%(lab,round(fr*100))))
    ba=b.get("mouillage_bascule");mc=b.get("moor_change")
    if mc:
        moor_line="<b>Mouillage :</b> %s cette nuit, puis <b>change vers %s</b> %s."%(mc["frm"],mc["to"],mc["quand"])
    elif ba:
        moor_line=("<b>Mouillage :</b> %s ce soir ; bascule vers <b>%s</b> %s vers %s, quand le vent passe au %s "
                   "(secteur exposé de %s)."%(best_soir, ba["to"], ba["jour"], ba["heure"], ba["dir"], best_soir))
    else:
        moor_line="<b>Mouillage :</b> %s, bien protégé sur toute la période (houle résiduelle comprise), pas de bascule nécessaire."%best_soir
    concl=["<b>%s :</b> %s. %s"%(jourC,nav["status"].lower(),nav["reason"])]
    if b.get("contexte"): concl.append("<b>Situation :</b> %s."%b["contexte"])
    concl.append(moor_line)
    if b["raf_max"]>=34: concl.append("<b>Coup de vent :</b> rafales %d kn, mer %.1f m. <font color='#B3261E'><b>Prudence maximale</b></font>."%(b["raf_max"],b["mer_max"]))
    elif b["raf_max"]>=30: concl.append("<b>Rafales :</b> jusqu'à %d kn, surtout au Cap Sicié, vigilance."%b["raf_max"])
    else: concl.append("<b>Mer :</b> %.1f m, conditions maniables."%b["mer_max"])
    if b["tendance"]: lab,fr=b["tendance"][0];concl.append("<b>Tendance :</b> %s, probabilité %d%%."%(lab.lower(),round(fr*100)))
    return [left,right],reco,concl

def synthese_telegram(b):
    nav=b["nav"];feu={"G":"🟢 FAVORABLE","A":"🟠 PRUDENCE","R":"🔴 DÉCONSEILLÉ"}[nav["color"]]
    bo=b.get("bms_officiel")
    if bo and bo.get("actif_zone"):
        bms="🟥 BMS OFFICIEL Météo-France : %s\n%s (jusqu'à %s)"%(bo["avis"],bo.get("zone_texte",""),bo.get("fin",""))
    elif bo:
        bms="🟠 BMS en Méditerranée (hors ta zone) : "+bo["avis"]
    elif b.get("bms_est"):
        bms="🟠 BMS probable : "+b["bms_est"]
    else:
        bms="🟢 Pas de BMS en cours (bulletin officiel vérifié)"
    vig=b.get("vigilance")
    vigline=("🟧 Vigilance officielle %s (Var/13) : %s"%(vig["max_label"], ", ".join("%s %s"%(k,v) for k,v in vig.get("phenos",{}).items()))) if (vig and vig.get("max_color",1)>=3) else None
    JOUR=("AUJOURD'HUI" if b.get("target")=="today" else "DEMAIN")
    hdr=("☀️ RAPPORT DU JOUR IZENAH · " if b.get("target")=="today" else "🌊 BRIEFING IZENAH · ")
    fiab=("Fiabilité %s (%d%%)"%(b["confiance"].lower(),b["confiance_pct"])) if b.get("confiance_pct") is not None else ("Fiabilité %s"%b["confiance"].lower())
    plage=("%d à %d nœuds"%(b["vent_lo"],b["vent_max"])) if b.get("vent_lo") and b["vent_lo"]<b["vent_max"] else ("jusqu'à %d nœuds"%b["vent_max"])
    lines=[hdr+b["generated"],
           "La Ciotat ↔ Les Embiez",
           "",
           "%s · %s"%(bms, fiab)] + ([vigline] if vigline else []) + [
           "",
           "▶ %s · Navigation %s"%(JOUR,feu),
           "Vent %s %s, rafales %d nœuds · Mer %.1f m"%(b["dom_dir"],plage,b["raf_max"],b["mer_max"])]
    if b.get("contexte"): lines.append("☁ %s"%b["contexte"])
    if b.get("p_raf30_tom") is not None:
        lines.append("Risque de rafales fortes (plus de 30 nœuds) : %d%% (%s)"%(b["p_raf30_tom"],p_word(b["p_raf30_tom"])))
    fen=b.get("fenetre")
    if fen and fen["kind"]=="ALL": lines.append("🟢 Favorable toute la journée")
    elif fen and fen["kind"]=="G": lines.append("🟢 Meilleure fenêtre de sortie : %s à %s"%(fen["frm"],fen["to"]))
    elif fen and fen["kind"]=="A": lines.append("🟠 Créneau le plus maniable : %s à %s"%(fen["frm"],fen["to"]))
    nuits=b.get("nuits") or []
    if len(nuits)==2:
        mc=b.get("moor_change")
        def _n(nu): return "%s (%s)"%(nu["best"],nu["verdict"].lower()) if not nu.get("port") else "%s au mieux — port conseillé"%nu["best"]
        mline="⚓ Cette nuit : %s · Demain nuit : %s"%(_n(nuits[0]),_n(nuits[1]))
        if mc: mline+="\n⚠️ Change de mouillage %s"%mc["quand"]
    else:
        mline="⚓ Mouillage conseillé : %s"%b["mouillage_best"]
    lines+=[mline,
           "",
           "🔗 Officiel Météo-France (secteur) : "+MF_LINK,
           "Détail complet dans le PDF ci-joint."]
    return "\n".join(lines)

def render(b, out):
    doc=SimpleDocTemplate(out,pagesize=A4,topMargin=9*mm,bottomMargin=8*mm,leftMargin=12*mm,rightMargin=12*mm,title="Briefing Izenah")
    W=doc.width;story=[]
    def secheader(title,sub=None,tab=GOLD):
        if sub: t=Table([["",Paragraph(title,sect),Paragraph(sub,subt)]],colWidths=[3.2*mm,W*0.5,W-3.2*mm-W*0.5]);extra=[("ALIGN",(2,0),(2,0),"RIGHT")]
        else: t=Table([["",Paragraph(title,sect)]],colWidths=[3.2*mm,W-3.2*mm]);extra=[]
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),tab),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(0,0),0),("LEFTPADDING",(1,0),(1,0),6),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]+extra));return t
    def icon_cell(icon,text,style,iw,tw):
        t=Table([[icon,Paragraph(text,style)]],colWidths=[iw,tw])
        t.setStyle(TableStyle([("LEFTPADDING",(0,0),(0,0),0),("RIGHTPADDING",(0,0),(0,0),0.6*mm),("LEFTPADDING",(1,0),(1,0),0),("RIGHTPADDING",(1,0),(1,0),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),("VALIGN",(0,0),(-1,-1),"MIDDLE")]));return t
    alert,reco,concl=narrative(b)
    # HEADER
    ht=S("ht",fontName="Helvetica-Bold",fontSize=16.5,textColor=colors.white,leading=18)
    hsx=S("hsx",fontName="Helvetica",fontSize=8.4,textColor=HexColor("#BFD6EA"),leading=11)
    hd=S("hd",fontName="Helvetica-Bold",fontSize=9,textColor=colors.white,alignment=2,leading=11.5)
    he=S("he",fontName="Helvetica-Oblique",fontSize=7.4,textColor=GOLD,alignment=2,leading=9.5)
    head=Table([[[Paragraph("BRIEFING MARINE&nbsp;&nbsp;<font color='#D6A93B'>IZENAH</font>",ht),
       Paragraph("La Ciotat &nbsp;•&nbsp; Bandol &nbsp;•&nbsp; Cap Sicié &nbsp;•&nbsp; Les Embiez &nbsp;|&nbsp; au mouillage, 24h",hsx)],
       [Paragraph(b["generated"],hd),Paragraph("briefing automatique · données réelles",he)]]],colWidths=[W*0.62,W*0.38])
    head.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),NAVY),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    story+=[head,HRFlowable(width="100%",thickness=2,color=GOLD,spaceAfter=5),AlertStrip(W,alert),Spacer(1,6)]
    # NAV + FIAB
    gp=5*mm;navw=(W-gp)*0.60;fiabw=(W-gp)*0.40
    conf=b["confiance"]
    conf_reason=b.get("conf_detail") or {"ÉLEVÉE":"Modèles d'accord, ensemble resserré.","MODÉRÉE":"Accord partiel entre modèles.","FAIBLE":"Modèles dispersés, à confirmer."}[conf]
    conf_status=("%s · %d%%"%(conf,b["confiance_pct"])) if b.get("confiance_pct") is not None else conf
    nav=StatusPanel(navw,"Navigation : peux-tu sortir ?",b["nav"]["status"],NAVCOL[b["nav"]["color"]],b["nav"]["reason"],[("favorable",CGd),("prudence",CAd),("déconseillé",CRd)])
    fiab=StatusPanel(fiabw,"Fiabilité : prévision sûre ?",conf_status,CONFCOL[conf],conf_reason,[("faible",CRd),("modérée",CAd),("élevée",CGd)])
    prow=Table([[nav,"",fiab]],colWidths=[navw,gp,fiabw]);prow.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story+=[prow,Spacer(1,6)]
    # MOUILLAGES
    story+=[secheader("Tes deux mouillages",sub="confort du soir et bascule"),Spacer(1,3)]
    nm=S("nm",fontName="Helvetica-Bold",fontSize=9,textColor=NAVY,leading=11)
    vw=S("vw",fontName="Helvetica-Bold",fontSize=8.4,alignment=2,leading=11)
    ax=S("ax",fontName="Helvetica",fontSize=7.3,textColor=INK,leading=9.6)
    def moor_card(m,cardw):
        abri,expo=ABRI.get(m["name"],("n/d","n/d"))
        verdict=verdict_of(m["frac"]);vcol=vcol_of(m["frac"])
        hh=Table([[Paragraph(m["name"],nm),Paragraph("<font color='%s'>%s</font>"%(vcol,verdict),vw)]],colWidths=[cardw*0.5,cardw*0.5])
        hh.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        txt=Paragraph("<font color='#1C7C54'>Abri : %s</font> &nbsp;·&nbsp; <font color='#B3261E'>Exposé : %s</font>"%(abri,expo),ax)
        inner=Table([[hh],[ComfortGauge(cardw-2,m["frac"])],[txt]],colWidths=[cardw])
        inner.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(0,0),0),("TOPPADDING",(0,1),(0,1),1),("BOTTOMPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,2),(0,2),1)]))
        card=Table([[inner]],colWidths=[cardw+10])
        card.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),HexColor("#F7FAFC")),("BOX",(0,0),(-1,-1),0.6,LINE),("ROUNDEDCORNERS",[5,5,5,5]),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]));return card
    cardw=(W-gp)/2-10
    ms=b["mouillages"][:2]
    while len(ms)<2: ms.append(ms[-1])
    mrow=Table([[moor_card(ms[0],cardw),"",moor_card(ms[1],cardw)]],colWidths=[(W-gp)/2,gp,(W-gp)/2])
    mrow.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story+=[mrow,Spacer(1,2)]
    nuits=b.get("nuits") or []
    if len(nuits)==2:
        mc=b.get("moor_change")
        if mc: chg="<font color='#B5740F'><b>Change de mouillage %s.</b></font>"%mc["quand"]
        else: chg="Pas de changement de mouillage nécessaire."
        def _np(nu):
            base="%s (<font color='%s'>%s</font>)"%(nu["best"],vcol_of(nu["frac"]),nu["verdict"].lower())
            return base+(" — <font color='#C02718'><b>port conseillé</b></font>" if nu.get("port") else "")
        nline="<b>Où dormir — cette nuit :</b> %s &nbsp;·&nbsp; <b>demain nuit :</b> %s — %s"%(_np(nuits[0]),_np(nuits[1]),chg)
        story+=[Paragraph(nline,body),Spacer(1,4)]
    else:
        story+=[Spacer(1,2)]
    rt=S("rt",fontName="Helvetica-Bold",fontSize=8,textColor=colors.white,leading=10)
    rb=S("rb",fontName="Helvetica",fontSize=8,textColor=colors.white,leading=10.6)
    def gpill(txt):
        st=S("gp",fontName="Helvetica-Bold",fontSize=6.4,textColor=NAVY,alignment=1)
        tb=Table([[Paragraph(txt,st)]],colWidths=[22*mm],rowHeights=[5*mm])
        tb.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),GOLD),("ROUNDEDCORNERS",[2.5,2.5,2.5,2.5]),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]));return tb
    rrows=[[Paragraph("RECOMMANDATION ET ANTICIPATION",rt),""]]
    for tag,txt in reco: rrows.append([gpill(tag),Paragraph(txt,rb)])
    recoT=Table(rrows,colWidths=[26*mm,W-26*mm])
    recoT.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),STEEL),("ROUNDEDCORNERS",[5,5,5,5]),("SPAN",(0,0),(1,0)),("LINEBEFORE",(0,0),(0,-1),3,GOLD),("LEFTPADDING",(0,0),(0,-1),9),("LEFTPADDING",(1,1),(1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),9),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,0),5),("TOPPADDING",(0,1),(-1,-1),2.5),("BOTTOMPADDING",(0,-1),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,0),3)]))
    story+=[recoT,Spacer(1,7)]
    # DETAIL
    story+=[secheader("Le détail des conditions",sub="cadence 2 heures, valeurs colorées selon les seuils"),Spacer(1,3)]
    cw=[15*mm,7*mm,28*mm,12*mm,7*mm,22*mm,12*mm,17*mm,26*mm,W-(15+7+28+12+7+22+12+17+26)*mm]
    hdr=[Paragraph("Heure",cH),Paragraph("Vent",cH),"",Paragraph("Raf.",cH),Paragraph("Houle",cH),"",Paragraph("Mer",cH),Paragraph("Air/Eau",cH),Paragraph("Ciel",cH),Paragraph("Press.",cH)]
    rows=[hdr]
    for d in b["detail"]:
        night=d["night"];bg=SLATE if night else colors.white;sty=wC if night else cC;wcl=WINDN if night else MARINE;hcl=TEALN if night else TEAL
        heure=icon_cell(WIcon("moon" if night else "sun",4.4*mm,bg=bg),"<b>%s</b>"%d["hh"],(wL if night else cL),5*mm,cw[0]-5*mm-1*mm)
        ciel=icon_cell(WIcon(d["ciel"],4.6*mm,bg=bg),d["ciel_lbl"],(wL if night else cL),5.4*mm,cw[8]-5.4*mm-1*mm)
        houle_txt="%s %s"%(d["houle_dir"],d.get("houle_p","") or d["houle"])
        air="%s°/%s°"%(d["air"] if d["air"] is not None else "?",d["eau"] if d["eau"] is not None else "?")
        rows.append([heure,Arrow(d["wdir"],5.4*mm,wcl),ventcell("%d à %d kn"%(d["vmin"],d["vmax"]),"%s %s"%(d["wdir"],d["force"]),wind_hex(d["vmax"],night),night),
                     colcell(str(d["gust"]),gust_hex(d["gust"],night)),Arrow(d["houle_dir"],5*mm,hcl),Paragraph(houle_txt,sty),
                     colcell(d["houle"],sea_hex(d["mer"],night)),Paragraph(air,sty),ciel,Paragraph(str(d["press"]) if d["press"] else "n/d",sty)])
    t=Table(rows,colWidths=cw,rowHeights=[6*mm]+[7.6*mm]*len(b["detail"]))
    ts=[("BACKGROUND",(0,0),(-1,0),BLUE),("ROUNDEDCORNERS",[4,4,4,4]),("SPAN",(1,0),(2,0)),("SPAN",(4,0),(5,0)),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LINEBELOW",(0,1),(-1,-2),0.4,LINE),("TOPPADDING",(0,0),(-1,-1),0.6),("BOTTOMPADDING",(0,0),(-1,-1),0.6),("LEFTPADDING",(0,1),(0,-1),3),("LEFTPADDING",(8,1),(8,-1),3)]
    for i,d in enumerate(b["detail"]):
        rr=i+1
        if d["night"]:ts.append(("BACKGROUND",(0,rr),(-1,rr),SLATE))
        elif i%2==1:ts.append(("BACKGROUND",(0,rr),(-1,rr),ZEBRA))
    t.setStyle(TableStyle(ts));story+=[t,Spacer(1,4)]
    fen="<b>Orage et grain :</b> risque <font color='#1C7C54'><b>%s</b></font> (CAPE max %d J/kg)."%(b["orage"],b["cape_max"]) if b["orage"]=="faible" else "<b>Orage et grain :</b> risque <font color='#B5740F'><b>%s</b></font> (CAPE max %d J/kg), surveille les développements."%(b["orage"],b["cape_max"])
    plage=("%d à %d kn selon les modèles"%(b["vent_lo"],b["vent_max"])) if b.get("vent_lo") and b["vent_lo"]<b["vent_max"] else ("jusqu'à %d kn"%b["vent_max"])
    story+=[Paragraph("<b>Vent dominant</b> de %s, %s (rafales %d). %s"%(b["dom_dir"],plage,b["raf_max"],fen),body),PageBreak()]
    # PAGE 2 — graphe
    ch=b["chart"]
    story+=[secheader("Le vent heure par heure",sub="La Ciotat • AROME 1,3 km, après le détail ci-dessus",tab=MARINE),Spacer(1,2)]
    story+=[WindChart(W,66*mm,ch["hours"],ch["mn"],ch["mx"],ch["mean"],ch["gust"],ch["night"],ch["dir"]),Spacer(1,3)]
    story+=[Paragraph("La <b>plage</b> bleutée montre le vent mini et maxi entre modèles : plus elle est étroite, plus c'est fiable. Quadrillage vertical = chaque heure. Zone grisée = la nuit. Échelle de droite = la force (Beaufort), en second plan.",small),Spacer(1,8)]
    # Consensus
    if b["consensus"]:
        story+=[secheader("Les prochains jours",sub="consensus des modèles, J+2 à J+5 · pastille = feu navigation",tab=STEEL),Spacer(1,3)]
        c2w=[10*mm,28*mm,W-(10+28+34+7+26+24)*mm,34*mm,7*mm,26*mm,24*mm]
        h2=[Paragraph("Dir.",cH),Paragraph("Jour",cH),Paragraph("Vent (plage)",cH),Paragraph("Rafales",cH),Paragraph("Houle",cH),"",Paragraph("Confiance",cH)]
        r2=[h2]
        def pillP(txt,col):
            st=S("p",fontName="Helvetica-Bold",fontSize=7.4,textColor=colors.white,alignment=1)
            tb=Table([[Paragraph(txt,st)]],colWidths=[20*mm],rowHeights=[5.4*mm])
            tb.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),col),("ROUNDEDCORNERS",[3,3,3,3]),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]));return tb
        NAVDOT={"G":CGd,"A":CAd,"R":CRd}
        for c in b["consensus"]:
            dayc=Paragraph("<font color='%s'><b>●</b></font> %s"%(NAVDOT.get(c.get("nav","G"),CAd),c["day"]),cL)
            r2.append([Arrow(c["wdir"],6*mm,MARINE),dayc,ventcell("%d à %d kn"%(c["vmin"],c["vmax"]),c["force"],wind_hex(c["vmax"],0)),
                       colcell((str(c["gust"])+" kn") if c["gust"] else "n/d",gust_hex(c["gust"] or 0,0)),Arrow(c["houle_dir"],5.6*mm,TEAL),Paragraph(c["houle"],cC),pillP(c["conf"],PILLCOL.get(c["conf"],AMBER))])
        t2=Table(r2,colWidths=c2w,rowHeights=[6.2*mm]+[10*mm]*len(b["consensus"]))
        t2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),STEEL),("ROUNDEDCORNERS",[4,4,4,4]),("SPAN",(4,0),(5,0)),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,ZEBRA]),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LINEBELOW",(0,1),(-1,-2),0.4,LINE),("LEFTPADDING",(1,1),(1,-1),3),("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)]))
        story+=[t2,Spacer(1,8)]
    # Tendance
    if b["tendance"]:
        story+=[secheader("La tendance à douze jours",sub="ensemble ECMWF, 51 scénarios",tab=MARINE),Spacer(1,3)]
        story+=[Paragraph("Au-delà du détail, la prévision se lit en probabilités (part des 51 scénarios franchissant le seuil). Confiance faible au-delà de J+7.",body),Spacer(1,4)]
        for lab,fr in b["tendance"]:
            col=RED if fr>=0.5 else AMBER
            pb=Table([[Paragraph(lab,body),ProbBar(fr,50*mm,fill=col)]],colWidths=[W-56*mm,56*mm])
            pb.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
            story+=[pb]
        story+=[Spacer(1,7)]
    # Conclusion
    ct=S("ct",fontName="Helvetica-Bold",fontSize=10,textColor=colors.white,leading=12)
    ci=S("ci",fontName="Helvetica",fontSize=8.7,textColor=HexColor("#142233"),leading=13)
    pts="".join("<font color='#D6A93B'><b>•</b></font>&nbsp; %s<br/>"%x for x in concl)
    cc=Table([[Paragraph("CE QUI MÉRITE ATTENTION",ct)],[Paragraph(pts,ci)]],colWidths=[W])
    cc.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),NAVY),("BACKGROUND",(0,1),(0,1),HexColor("#E9F1F8")),("LINEBEFORE",(0,1),(0,1),3,GOLD),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(0,0),5),("BOTTOMPADDING",(0,0),(0,0),5),("TOPPADDING",(0,1),(0,1),7),("BOTTOMPADDING",(0,1),(0,1),8)]))
    story+=[cc,Spacer(1,6),HRFlowable(width="100%",thickness=0.5,color=LINE,spaceAfter=3)]
    story+=[Paragraph("<b>Méthode :</b> 5 modèles confrontés et pondérés (AROME 1,3 km, ARPEGE, ECMWF, ICON, GFS) + ensemble ECMWF 51 scénarios ; le badge Navigation retient le scénario haut crédible, jamais la moyenne. BMS et Vigilance Météo-France font foi. Flèches : <font color='#1B6CA8'><b>•</b></font> vent, <font color='#0E9AA7'><b>•</b></font> houle.",small)]
    story+=[Paragraph("<b>Bulletin officiel Météo-France</b> (secteur Marseille / La Ciotat) : <a href='%s'><font color='#1B6CA8'>%s</font></a>"%(MF_LINK,MF_LINK),small)]
    doc.build(story)
    return out

if __name__=="__main__":
    import sys
    b=build_brief()
    out=sys.argv[1] if len(sys.argv)>1 else "/sessions/hopeful-sweet-cray/mnt/Le Mérovingien/Briefing_Izenah.pdf"
    render(b,out)
    print("PDF ->",out)
    print("---- SYNTHESE TELEGRAM ----")
    print(synthese_telegram(b))

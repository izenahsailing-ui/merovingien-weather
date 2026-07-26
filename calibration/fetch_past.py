# -*- coding: utf-8 -*-
"""Recupere les ANCIENNES SORTIES DE MODELES au point du Bec de l'Aigle,
sur la meme periode que l'observation, pour mesurer leur erreur reelle."""
import urllib.request, urllib.parse, json, time, datetime, os

LAT, LON = 43.174667, 5.574167          # station Bec de l'Aigle
MODELS = ["meteofrance_arome_france_hd", "meteofrance_arpege_europe",
          "ecmwf_ifs025", "icon_eu", "icon_global", "gfs_seamless"]

def fetch(url, tries=4):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "izenah-calib/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except Exception as ex:
            last = ex
            time.sleep(4 * (k + 1))
    raise RuntimeError("fetch: %s" % last)

def periode(d0, d1):
    q = dict(latitude=LAT, longitude=LON, start_date=d0, end_date=d1,
             hourly="wind_speed_10m,wind_gusts_10m,wind_direction_10m",
             models=",".join(MODELS), wind_speed_unit="ms", timezone="UTC")
    return fetch("https://historical-forecast-api.open-meteo.com/v1/forecast?"
                 + urllib.parse.urlencode(q))

if __name__ == "__main__":
    out = {}
    d = datetime.date(2025, 1, 1)
    fin = datetime.date(2026, 7, 25)
    while d < fin:
        z = min(d + datetime.timedelta(days=90), fin)
        print("  %s -> %s" % (d, z), flush=True)
        try:
            r = periode(d.isoformat(), z.isoformat())
            H = r["hourly"]
            for k, v in H.items():
                out.setdefault(k, []).extend(v)
        except Exception as ex:
            print("    echec:", ex, flush=True)
        d = z + datetime.timedelta(days=1)
        time.sleep(1)
    json.dump(out, open("prev_bec.json", "w"))
    print("heures recuperees :", len(out.get("time", [])))

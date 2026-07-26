# Calibration mesuree

Ce dossier contient la confrontation des modeles a l observation reelle.

## Donnees

- **Observation** : station Meteo-France **Bec de l Aigle (13028001)**, a 2,7 km
  de La Ciotat, altitude 316 m. Donnees horaires publiques, gratuites,
  telechargees sur le S3 public de Meteo-France
  (`H_13_latest-2025-2026.csv.gz`). Colonnes FF (vent moyen 10 min, m/s),
  DD (direction), FXI (rafale maximale instantanee de l heure).
  **13 701 heures** du 1er janvier 2025 au 26 juillet 2026.

- **Previsions** : anciennes sorties de modeles au meme point, via
  `historical-forecast-api.open-meteo.com`. **13 704 heures**, memes six
  modeles que la production.

## Resultat principal

Tous les modeles **sous-estiment** le vent a ce point, de 2,4 a 3,3 m/s, ce qui
est attendu pour un sommet de cap : la maille du modele moyenne un relief que
l anemometre ne moyenne pas.

Erreur quadratique (m/s), vent moyen puis rafales :

| Modele          | vent RMSE | rafales RMSE |
|-----------------|-----------|--------------|
| ARPEGE 11 km    | **3,82**  | 4,84         |
| AROME 1,5 km    | 4,02      | 4,14         |
| ICON global     | 4,17      | **3,84**     |
| ECMWF 25 km     | 4,19      | 4,57         |
| GFS 13 km       | 4,58      | 5,47         |
| ICON-EU 7 km    | 4,62      | 4,76         |

## Ce que la mesure a change dans le moteur

1. **Les poids ne sont plus poses au juge.** L ancienne ponderation
   (AROME 3, ARPEGE 2, ECMWF 2, ICON 1, GFS 1) est infirmee : ARPEGE fait
   legerement mieux qu AROME sur le vent moyen, et **ICON global est le
   meilleur sur les rafales**. Les poids valent desormais l inverse de
   l erreur quadratique mesuree, separement pour le vent et pour la rafale.
2. **GFS est confirme comme le pire sur les rafales** (RMSE 5,47), ce qui
   justifie le garde-fou introduit apres l observation de rapports
   rafale/vent de 0,46 a 4,37 sur ses sorties.
3. **Le garde-fou a ete elargi** : le rapport rafale/vent reellement observe
   monte a 2,85 au 95e centile et 4,15 au 99e. Les bornes passent de
   [1,05 ; 2,60] a [1,05 ; 3,20] pour ne plus ecarter de vraies rafales.
4. **L effet de maille a ete adouci** : la mesure ne confirme pas la
   domination de la maille fine sur ce point.

## Ce que la mesure ne permet PAS encore

Le biais par secteur est fort et tres structure (de **-4,09 m/s par Est** a
**+0,65 m/s par Sud-Ouest**), mais il est mesure sur un **sommet a 316 m**.
Il documente l ampleur de l effet de site ; il n est **pas** applique au
mouillage, qui est au niveau de la mer. Il le sera le jour ou une observation
au ras de l eau sera disponible, ce qui demande la cle Meteo-France
(`mf_apikey.txt` est toujours vide) ou une bouee.

## Rejouer

    python3 fetch_past.py     # recupere les anciennes sorties de modeles
    python3 analyse.py        # confronte a l observation et recalcule les poids

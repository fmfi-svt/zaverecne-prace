# Záverečné práce

Skript, ktorý z AISu stiahne k vybranému študijnému programu pre každého študenta:

- protokol o originalite (`originalita.pdf`),
- posudok vedúceho (`veduci.pdf`),
- posudok oponenta (`oponent.pdf`),
- záverečnú prácu (`praca.pdf`).

Súbory sa uložia do `output/<Priezvisko_Meno>__<Subor>.pdf`.

## Inštalácia

```bash
uv sync
```

## Spustenie

```bash
export AIS_USERNAME="priezvisko1" AIS_PASSWORD
read -s AIS_PASSWORD
export SP="DAV"          # skratka študijného programu (voliteľné, default DAV)
export OUTPUT="output"   # výstupný priečinok (voliteľné)

uv run main.py
```

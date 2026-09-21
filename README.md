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
export ROOT_URL="https://zaverecne.example.sk/"
export FLASK_SECRET_KEY="$(openssl rand -hex 32)"
export AIS_URL="https://ais2.uniba.sk/"
# either this, or put it into var/saml/andrvotr_api_key
export ANDRVOTR_API_KEY="..."
# optional; otherwise python3-saml reads var/saml/certs/sp.{key,crt}
uv run generate_saml_certs.py >> .env
set -a; . ./.env; set +a

uv run flask --app app run
```

For shell export output instead:

```bash
eval "$(uv run generate_saml_certs.py --shell)"
```

SAML files expected by the app unless provided through env:

```txt
var/saml/idp-metadata.xml
var/saml/certs/sp.key
var/saml/certs/sp.crt
```

To write cert files instead of env vars:

```bash
uv run generate_saml_certs.py --out var/saml/certs
```

Register SP metadata from `https://zaverecne.example.sk/saml_sp` and ask IdP to release
`uid` plus `tag:fmfi-svt.github.io,2024:andrvotr-authority-token`.

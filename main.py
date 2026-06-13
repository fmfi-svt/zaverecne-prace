import os
from requests import Response
from pathlib import Path
from aisikl.app import Application
from fladgejt.login import create_client

STUDIJNY_PROGRAM = os.environ.get("SP", "DAV")
AIS_USERNAME = os.environ.get("AIS_USERNAME")
AIS_PASSWORD = os.environ.get("AIS_PASSWORD")
AIS_URL = os.environ.get("AIS_URL", "https://ais2.uniba.sk/")
OUTPUT = Path(os.environ.get("OUTPUT", "output"))
OUTPUT.mkdir(exist_ok=True, parents=True)

VSES057 = "/ais/servlets/WebUIServlet?appClassName=ais.gui.vs.es.VSES057App&kodAplikacie=VSES057&uiLang=SK"
SUBORY = [
    ("u_tlacVysledkuOriginalityAction", "originalita"),
    ("u_0pdfPosudokPrevziatMI", "veduci"),
    ("u_1pdfPosudokPrevziatMI", "oponent"),
    ("u_prevziatPracuAction", "praca"),
]

client = create_client(
    {
        "title": AIS_URL,
        "login_types": ["saml_password"],
        "ais_cookie": "JSESSIONID",
        "ais_url": AIS_URL,
    },
    {
        "type": "saml_password",
        "username": AIS_USERNAME,
        "password": AIS_PASSWORD,
    },
)

# otvoríme VSES057
app, ops = Application.open(client.context, VSES057)
app.awaited_open_main_dialog(ops)
assert app.d is not None  # aby pyright nekričal na app.d

# vymažeme predvolenú osobu
app.d.zmazatOsobu2Button.click()

# otvoríme dialóg na výber ŠP
with app.collect_operations() as ops:
    app.d.vybratSPButton.click()
    app.awaited_open_dialog(ops)

# nájdeme v tabuľke chcený ŠP a zavrieme dialóg
rows = app.d.vyberTable.all_rows()
index = None
for i, row in enumerate(rows):
    if row["skratka"] == STUDIJNY_PROGRAM:
        index = i
        break

if index is None:
    raise ValueError("Neplatný študíjny program.")

app.d.vyberTable.select(index)
with app.collect_operations() as ops:
    app.d.enterButton.click()
    app.awaited_close_dialog(ops)

# Načítame tabuľku
app.d.zobrazit2Button.click()
zaverecne_prace = app.d.zaverecnePraceTable.all_rows()

for i, praca in enumerate(zaverecne_prace):
    # Otvoríme "Hodnotenie záverečnej práce, posudok"
    app.d.zaverecnePraceTable.select(i)
    with app.collect_operations() as ops:
        app.d.hodnoteniePraceAction.execute()
        if ops[0].method != "confirmBox":
            app.awaited_open_dialog(ops)

    # Je možné, že riadok je zamknutý, zobrazíme si ho aj tak.
    if ops[0].method == "confirmBox":
        with app.collect_operations() as ops:
            app.confirm_box(2)
            app.awaited_open_dialog(ops)

    student_prefix = f"{praca['studentPriezvisko']}_{praca['studentMeno']}"
    print(student_prefix)

    for action, filename in SUBORY:
        with app.collect_operations() as ops:
            component = getattr(app.d, action, None)
            if not component:
                continue

            if action.endswith("Action"):
                component.execute()
            else:
                component.click()

            # AIS nám vynadá, že daný objekt neexistuje.
            if ops[0].method == "messageBox":
                continue

            resp: Response = app.awaited_shell_exec(ops)
            if resp.status_code != 200:
                continue
            if len(resp.content) == 0:
                continue

        (OUTPUT / f"{student_prefix}__{filename}.pdf").write_bytes(resp.content)
        print(" -", filename)

    with app.collect_operations() as ops:
        app.d.closeButton.click()
        app.awaited_close_dialog(ops)

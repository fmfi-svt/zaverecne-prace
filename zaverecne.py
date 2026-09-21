from pathlib import Path

import pikepdf
from aisikl.app import Application
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer
from requests import Response

VSES057 = "/ais/servlets/WebUIServlet?appClassName=ais.gui.vs.es.VSES057App&kodAplikacie=VSES057&uiLang=SK"
SUBORY = [
    ("u_tlacVysledkuOriginalityAction", "originalita"),
    ("u_0pdfPosudokPrevziatMI", "veduci"),
    ("u_1pdfPosudokPrevziatMI", "oponent"),
    ("u_prevziatPracuAction", "praca"),
]


def download_documents(
    ctx,
    *,
    academic_year: str,
    faculty_work: str,
    faculty_study_programme: str,
    study_programme: str,
    output: Path,
):

    # otvoríme VSES057
    app, ops = Application.open(ctx, VSES057)
    app.awaited_open_main_dialog(ops)
    assert app.d is not None  # aby pyright nekričal na app.d

    try:
        # vyberieme fakultu práce
        index = None
        for i, item in enumerate(app.d.fakultaComboBox.options):
            if item.id == faculty_work:
                index = i

        if index is None:
            raise ValueError("Neplatná fakulta práce.")

        app.d.fakultaComboBox.select(index)
        app.d.potvrditFakultuButton.click()

        # vyberieme akademický rok
        index = None
        for i, item in enumerate(app.d.akademickyRok2ComboBox.options):
            if item.title == academic_year:
                index = i

        if index is None:
            raise ValueError("Neplatný akademický rok.")

        app.d.akademickyRok2ComboBox.select(index)
        app.d.c5Button.click()

        # vymažeme predvolenú osobu a stredisko
        app.d.zmazatOsobu2Button.click()
        app.d.stredisko2ComboBox.select(0)

        # otvoríme dialóg na výber ŠP
        with app.collect_operations() as ops:
            app.d.vybratSPButton.click()
            app.awaited_open_dialog(ops)

        # nájdeme fakultu ŠP
        index = None
        for i, item in enumerate(app.d.fakultaComboBox.options):
            if item.id == faculty_study_programme:
                index = i

        if index is None:
            raise ValueError("Neplatná fakulta študijného programu.")

        app.d.fakultaComboBox.select(index)
        app.d.zobrazVyberButton.click()

        # nájdeme v tabuľke chcený ŠP a zavrieme dialóg
        rows = app.d.vyberTable.all_rows()
        index = None
        for i, row in enumerate(rows):
            if row["skratka"] == study_programme:
                index = i
                break

        if index is None:
            raise ValueError("Neplatný študijný program.")

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

                output_filename = f"{student_prefix}__{filename}.pdf"
                (output / output_filename).write_bytes(resp.content)

            with app.collect_operations() as ops:
                app.d.closeButton.click()
                app.awaited_close_dialog(ops)
    finally:
        app.force_close()


def merge_originality_reports(directory: Path, pages_per_file: int = 2):
    output_path = directory / "__originalita.pdf"
    input_files = sorted(
        p for p in directory.glob("*__originalita.pdf") if p != output_path
    )

    with pikepdf.Pdf.new() as merged:
        for pdf_path in input_files:
            with pikepdf.open(pdf_path) as src:
                for page in src.pages[:pages_per_file]:
                    merged.pages.append(page)

        merged.save(output_path)


TITLE_PAGE_KEYWORDS = (
    "školiteľ",
    "školiace pracovisko",
    "študijný odbor",
    "študijný program",
    "study programme",
    "field of study",
    "department",
    "supervisor",
)


def _find_title_page(pdf_path: Path, max_page: int = 10) -> int | None:

    for i, page in enumerate(extract_pages(str(pdf_path))):
        if i >= max_page:
            break
        text = "".join(
            el.get_text() for el in page if isinstance(el, LTTextContainer)
        ).lower()
        if any(kw in text for kw in TITLE_PAGE_KEYWORDS):
            return i
    return None


def merge_title_pages(directory: Path):
    output_path = directory / "__titulne.pdf"
    input_files = sorted(directory.glob("*__praca.pdf"))

    missing: list[str] = []
    with pikepdf.Pdf.new() as merged:
        for pdf_path in input_files:
            index = _find_title_page(pdf_path)
            if index is None:
                missing.append(pdf_path.name)
                continue
            with pikepdf.open(pdf_path) as src:
                merged.pages.append(src.pages[index])

        merged.save(output_path)

import asyncio
from abc import ABC
from pathlib import Path

import pikepdf
from aisikl.app import Application
from aisikl.components.action import Action
from aisikl.components.button import Button
from aisikl.components.combobox import ComboBox
from aisikl.components.menuitem import MenuItem
from aisikl.components.table import Table
from aisikl.context import Context
from aisikl.dialog import Dialog
from aisikl.operations import CloseDialogOp, ConfirmBoxOp, MessageBoxOp, OpenDialogOp, ShellExecOp
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer

VSES057 = "/ais/servlets/WebUIServlet?appClassName=ais.gui.vs.es.VSES057App&kodAplikacie=VSES057&uiLang=SK"
SUBORY = [
    ("u_tlacVysledkuOriginalityAction", "originalita"),
    ("u_0pdfPosudokPrevziatMI", "veduci"),
    ("u_1pdfPosudokPrevziatMI", "oponent"),
    ("u_prevziatPracuAction", "praca"),
]


class EvidenciaZaverecnychPracDialogsType(ABC, Dialog):
    akademickyRok2ComboBox: ComboBox
    c5Button: Button
    closeButton: Button
    enterButton: Button
    fakultaComboBox: ComboBox
    hodnoteniePraceAction: Action
    potvrditFakultuButton: Button
    stredisko2ComboBox: ComboBox
    vyberTable: Table
    vybratSPButton: Button
    zaverecnePraceTable: Table
    zmazatOsobu2Button: Button
    zobrazVyberButton: Button
    zobrazit2Button: Button


def download_documents(
    ctx: Context,
    *,
    academic_year: str,
    faculty_work: str,
    faculty_study_programme: str,
    study_programme: str,
    output: Path,
) -> None:
    asyncio.run(download_documents_async(
        ctx=ctx,
        academic_year=academic_year,
        faculty_work=faculty_work,
        faculty_study_programme=faculty_study_programme,
        study_programme=study_programme,
        output=output,
    ))


async def download_documents_async(
    ctx: Context,
    *,
    academic_year: str,
    faculty_work: str,
    faculty_study_programme: str,
    study_programme: str,
    output: Path,
) -> None:

    # otvoríme VSES057
    app, ops = await Application[EvidenciaZaverecnychPracDialogsType].open(ctx, VSES057)
    await ops.expect_one(OpenDialogOp).perform()

    try:
        # vyberieme fakultu práce
        index = None
        for i, item in enumerate(app.d.fakultaComboBox.options):
            if item.id == faculty_work:
                index = i

        if index is None:
            raise ValueError("Neplatná fakulta práce.")

        await app.d.fakultaComboBox.select(index)
        await app.d.potvrditFakultuButton.click()

        # vyberieme akademický rok
        index = None
        for i, item in enumerate(app.d.akademickyRok2ComboBox.options):
            if item.title == academic_year:
                index = i

        if index is None:
            raise ValueError("Neplatný akademický rok.")

        await app.d.akademickyRok2ComboBox.select(index)
        await app.d.c5Button.click()

        # vymažeme predvolenú osobu a stredisko
        await app.d.zmazatOsobu2Button.click()
        await app.d.stredisko2ComboBox.select(0)

        # otvoríme dialóg na výber ŠP
        ops = await app.d.vybratSPButton.click(return_ops=True)
        await ops.expect_one(OpenDialogOp).perform()

        # nájdeme fakultu ŠP
        index = None
        for i, item in enumerate(app.d.fakultaComboBox.options):
            if item.id == faculty_study_programme:
                index = i

        if index is None:
            raise ValueError("Neplatná fakulta študijného programu.")

        await app.d.fakultaComboBox.select(index)
        await app.d.zobrazVyberButton.click()

        # nájdeme v tabuľke chcený ŠP a zavrieme dialóg
        rows = await app.d.vyberTable.all_rows()
        index = None
        for i, row in enumerate(rows):
            if row["skratka"] == study_programme:
                index = i
                break

        if index is None:
            raise ValueError("Neplatný študijný program.")

        await app.d.vyberTable.select(index)
        ops = await app.d.enterButton.click(return_ops=True)
        await ops.expect_one(CloseDialogOp).perform()

        # Načítame tabuľku
        await app.d.zobrazit2Button.click()
        zaverecne_prace = await app.d.zaverecnePraceTable.all_rows()

        for i, praca in enumerate(zaverecne_prace):
            # Otvoríme "Hodnotenie záverečnej práce, posudok"
            await app.d.zaverecnePraceTable.select(i)
            ops = await app.d.hodnoteniePraceAction.execute(return_ops=True)

            # Je možné, že riadok je zamknutý, zobrazíme si ho aj tak.
            if ops.has_types(ConfirmBoxOp):
                ops = await ops.expect_one(ConfirmBoxOp).reply(ConfirmBoxOp.Option.YES, return_ops=True)

            # Či už hneď, alebo po potvrdení, mal by sa otvoriť nový dialóg.
            await ops.expect_one(OpenDialogOp).perform()

            student_prefix = f"{praca['studentPriezvisko']}_{praca['studentMeno']}"

            for action, filename in SUBORY:
                component = app.d.components.get(action)
                if not component:
                    continue

                if isinstance(component, Action):
                    ops = await component.execute(return_ops=True)
                elif isinstance(component, MenuItem):
                    ops = await component.click(return_ops=True)
                else:
                    raise TypeError(repr(component))

                # AIS nám vynadá, že daný objekt neexistuje.
                if ops.has_types(MessageBoxOp):
                    continue

                resp = await ops.expect_one(ShellExecOp).download()
                if resp.status_code != 200:
                    continue
                if len(resp.content) == 0:
                    continue

                output_filename = f"{student_prefix}__{filename}.pdf"
                (output / output_filename).write_bytes(resp.content)

            ops = await app.d.closeButton.click(return_ops=True)
            await ops.expect_one(CloseDialogOp).perform()
    finally:
        await app.force_close()


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

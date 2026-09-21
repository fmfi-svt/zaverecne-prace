import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, send_file, session
from werkzeug.exceptions import HTTPException

from andrvotr_saml import ais_context, register, require_login
from zaverecne import download_documents, merge_originality_reports, merge_title_pages

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]
register(app)


@app.context_processor
def inject_template_context():
    return {"footer_year": datetime.now().year, "username": session.get("uid")}


@app.get("/")
@require_login
def index():
    now = datetime.now()
    year = now.year if now.month >= 9 else now.year - 1
    return render_template(
        "form.html", academic_year=f"{year}/{year + 1}"
    )


@app.post("/")
@require_login
def download():
    ctx = ais_context()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        download_documents(
            ctx,
            academic_year=request.form["academic_year"],
            faculty_work=request.form["faculty_work"],
            faculty_study_programme=request.form["faculty_study_programme"],
            study_programme=request.form["studijny_program"],
            output=tmpdir_path,
        )
        merge_originality_reports(tmpdir_path)
        merge_title_pages(tmpdir_path)

        with zipfile.ZipFile(
            tmpdir_path / "output.zip", "w", zipfile.ZIP_DEFLATED
        ) as zf:
            for file in tmpdir_path.iterdir():
                if not file.is_file():
                    continue
                if file.name == "output.zip":
                    continue
                zf.write(file, file.name)

        return send_file(tmpdir_path / "output.zip")


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e

    return render_template("error.html", error=e), 500

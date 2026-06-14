from flask import Flask, render_template
from datetime import datetime

app = Flask(__name__)


@app.context_processor
def inject_year():
    return dict(footer_year=datetime.now().year)


@app.route("/")
def hello_world():
    return render_template("form.html")

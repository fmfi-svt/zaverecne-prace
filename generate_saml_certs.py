#!/usr/bin/env python3
import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate self-signed SAML SP cert/key")
    parser.add_argument("--days", type=int, default=3650)
    parser.add_argument("--subject", default="/CN=saml-sp")
    parser.add_argument("--out", type=Path, help="write var/saml/certs/sp.{crt,key}")
    parser.add_argument("--shell", action="store_true", help="print export commands instead of .env lines")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        key = Path(tmp) / "sp.key"
        cert = Path(tmp) / "sp.crt"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:3072",
                "-nodes",
                "-days",
                str(args.days),
                "-subj",
                args.subject,
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
        )

        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "sp.key").write_bytes(key.read_bytes())
            (args.out / "sp.crt").write_bytes(cert.read_bytes())
            return

        prefix = "export " if args.shell else ""
        print(prefix + "SAML_SP_KEY=" + json.dumps(key.read_text()))
        print(prefix + "SAML_SP_CERT=" + json.dumps(cert.read_text()))


if __name__ == "__main__":
    main()

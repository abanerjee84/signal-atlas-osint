"""Audit installed Python dependencies with OS trust roots, including enterprise certificates."""

import os
import ssl
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
bundle = root / "data/audit-ca.pem"
bundle.parent.mkdir(exist_ok=True)
certificates = ssl.create_default_context().get_ca_certs(binary_form=True)
bundle.write_text(
    "".join(ssl.DER_cert_to_PEM_cert(certificate) for certificate in certificates), encoding="ascii"
)
environment = dict(os.environ, REQUESTS_CA_BUNDLE=str(bundle), SSL_CERT_FILE=str(bundle))
raise SystemExit(
    subprocess.call(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--format",
            "json",
            "--output",
            str(root / "docs/python-audit.json"),
        ],
        env=environment,
    )
)

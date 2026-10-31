"""Exclude the trust anchors used by compromised eMudhra intermediate CAs."""

import hashlib
from pathlib import Path
import re
import ssl


BLOCKED = {
    "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4",
    "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b",
}
CERTIFICATE = re.compile(
    rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL
)


def fingerprint(pem):
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.decode("ascii"))).hexdigest()


def main():
    config = Path("/etc/ca-certificates.conf")
    lines = []
    for line in config.read_text().splitlines(keepends=True):
        name = line.strip()
        if name and not name.startswith(("#", "!")):
            certificate = Path("/usr/share/ca-certificates") / name
            if any(
                fingerprint(match[0]) in BLOCKED
                for match in CERTIFICATE.finditer(certificate.read_bytes())
            ):
                line = "!" + line
        lines.append(line)
    config.write_text("".join(lines))


if __name__ == "__main__":
    main()

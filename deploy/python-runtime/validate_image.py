"""Check a runtime patch against its immutable application image."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parent
INVENTORY = r"""
import base64, hashlib, importlib, importlib.metadata as md, json, os
from pathlib import Path
import ssl, subprocess, sys
for name in ['_ssl','_hashlib','_sqlite3','_bz2','_lzma','_ctypes','pyexpat','unicodedata','_decimal','readline']:
    importlib.import_module(name)
files = {}
for p in sorted(Path('/app').rglob('*')):
    if p.is_symlink(): files[str(p.relative_to('/app'))] = 'link:' + os.readlink(p)
    elif p.is_file(): files[str(p.relative_to('/app'))] = hashlib.sha256(p.read_bytes()).hexdigest()
packages = {d.metadata['Name'].lower().replace('_','-'): d.version for d in md.distributions()}
record_errors = []
if 'certifi' in packages:
    for item in md.distribution('certifi').files:
        if item.hash:
            value = hashlib.new(item.hash.mode, item.locate().read_bytes()).digest()
            if base64.urlsafe_b64encode(value).rstrip(b'=').decode() != item.hash.value:
                record_errors.append(str(item))
bundles = {'system': ssl.get_default_verify_paths().cafile,
           'pip': '/usr/local/lib/python3.11/site-packages/pip/_vendor/certifi/cacert.pem'}
if 'certifi' in packages:
    import certifi
    bundles['certifi'] = certifi.where()
if 'botocore' in packages:
    from web_search_web_model.archive.store import ObjectStore
    from botocore.httpsession import get_cert_path
    client = ObjectStore.from_env().client
    bundles['botocore-effective'] = get_cert_path(client._endpoint.http_session._verify)
    assert client._endpoint.http_session._verify is not False
bundles = {name: str(Path(path).resolve()) for name,path in bundles.items()}
print(json.dumps({'python':sys.version.split()[0], 'openssl':ssl.OPENSSL_VERSION,
                  'files':files,'packages':packages,'certifi_record_errors':record_errors,
                  'bundles':bundles,'native_packages':subprocess.check_output(
                  ['dpkg-query','-W','-f=${Package}=${Version}\n'],text=True)}))
"""

CHAINS = r"""
import datetime, json, os
from pathlib import Path
import re, ssl, subprocess, tempfile
bundles = json.loads(os.environ['VALIDATION_BUNDLES'])
certificate = re.compile(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',re.S)
results = {}
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    for name,bundle in bundles.items():
        checks = []
        for chain in [*sorted(Path('/fixtures/chains').glob('*.pem')), Path('/fixtures/positive-control.pem')]:
            blocks = certificate.findall(chain.read_text())
            assert len(blocks) >= 2
            (tmp/'leaf.pem').write_text(blocks[0]+'\n')
            (tmp/'intermediates.pem').write_text('\n'.join(blocks[1:])+'\n')
            start = subprocess.check_output(['openssl','x509','-in',str(tmp/'leaf.pem'),'-noout','-startdate'],text=True).strip().split('=',1)[1]
            when = int(ssl.cert_time_to_seconds(start))+3600
            verify = subprocess.run(['openssl','verify','-no-CApath','-no-CAstore','-CAfile',bundle,
                '-attime',str(when),'-untrusted',str(tmp/'intermediates.pem'),str(tmp/'leaf.pem')],capture_output=True,text=True)
            positive = chain.name == 'positive-control.pem'
            if positive: assert verify.returncode == 0, 'Valid public control rejected by '+name
            elif verify.returncode:
                assert 'error 20 at' in verify.stderr or 'error 19 at' in verify.stderr, 'Unexpected chain failure'
            checks.append({'positive':positive,'accepted':verify.returncode==0})
        results[name] = {'rejected_compromised':sum(not x['accepted'] for x in checks if not x['positive']),
                         'negative_cases':sum(not x['positive'] for x in checks), 'valid_public_chain_accepted':True}
print(json.dumps(results))
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--output")
    args = parser.parse_args()
    original = json.loads((ROOT / "images.json").read_text())[args.service]
    docker = shlex.split(args.docker)

    def run(*command, **kwargs):
        return subprocess.check_output([*docker, *command], text=True, **kwargs)

    def inspect(image):
        return json.loads(run("image", "inspect", image))[0]["Config"]

    def snapshot(image):
        return json.loads(
            run(
                "run",
                "--rm",
                "--network=none",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "-e",
                "R2_BUCKET=validation",
                "-e",
                "R2_ENDPOINT_URL=https://dummy.r2.cloudflarestorage.com",
                "-e",
                "R2_ACCESS_KEY_ID=dummy",
                "-e",
                "R2_SECRET_ACCESS_KEY=dummy",
                "--entrypoint",
                "/app/.venv/bin/python",
                image,
                "-c",
                INVENTORY,
            )
        )

    before, after = snapshot(original["image"]), snapshot(args.candidate)
    assert after["python"] == "3.11.18"
    assert before["native_packages"] == after["native_packages"]
    assert before["openssl"] == after["openssl"]
    expected_packages = {**before["packages"]}
    if "certifi" in expected_packages:
        expected_packages["certifi"] = "2026.10.19"
    assert after["packages"] == expected_packages
    assert not after["certifi_record_errors"]

    def application_files(files):
        return {
            path: value
            for path, value in files.items()
            if not path.startswith(".venv/lib/python3.11/site-packages/certifi/")
            and not path.startswith(".venv/lib/python3.11/site-packages/certifi-")
        }

    unchanged = application_files(before["files"])
    assert unchanged == application_files(after["files"]), (
        "Application or other dependency files changed"
    )
    old_config, new_config = inspect(original["image"]), inspect(args.candidate)
    for key in ["User", "Cmd", "Entrypoint", "WorkingDir", "ExposedPorts", "Volumes"]:
        assert old_config.get(key) == new_config.get(key), key
    old_env = dict(item.split("=", 1) for item in old_config["Env"])
    expected_env = {
        **old_env,
        "PYTHON_VERSION": "3.11.18",
        "PYTHON_SHA256": "9120e0a653868f6e3698d36cdd99e5a58903ec9469e448f21d98f7b16d8fa290",
        "AWS_CA_BUNDLE": "/etc/ssl/certs/ca-certificates.crt",
    }
    assert dict(item.split("=", 1) for item in new_config["Env"]) == expected_env
    assert (
        new_config["Labels"]["org.opencontainers.image.application.revision"]
        == original["application_commit"]
    )
    if "botocore-effective" in after["bundles"]:
        assert after["bundles"]["botocore-effective"] == after["bundles"]["system"]

    verification = json.loads(
        run(
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--mount",
            f"type=bind,src={ROOT / 'tests'},dst=/fixtures,readonly",
            "-e",
            "VALIDATION_BUNDLES=" + json.dumps(after["bundles"]),
            "--entrypoint",
            "/app/.venv/bin/python",
            args.candidate,
            "-c",
            CHAINS,
        )
    )
    for checks in verification.values():
        assert checks["negative_cases"] == checks["rejected_compromised"] == 16
    result = {
        "service": args.service,
        "python": after["python"],
        "application_commit": original["application_commit"],
        "application_and_other_dependency_files_preserved": len(unchanged),
        "native_packages_and_openssl_preserved": True,
        "certifi": after["packages"].get("certifi"),
        "certifi_record_valid": True,
        "commands_user_environment_preserved": True,
        "botocore_uses_system_ca": "botocore-effective" in after["bundles"],
        "certificate_chains": verification,
    }
    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()

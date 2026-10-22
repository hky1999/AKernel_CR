#!/usr/bin/env python3
"""Prepare private SDK credentials and a TLS-verified port-forward in the lab."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import ssl
import subprocess
import sys
import time


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(data)


def identity(pid):
    stat = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "start_ticks": stat[19]}


def tls_probe(ca):
    context = ssl.create_default_context(cafile=str(ca))
    deadline = time.monotonic() + 60
    while True:
        try:
            with socket.create_connection(("127.0.0.1", 18443), timeout=2) as connection:
                with context.wrap_socket(connection, server_hostname="localhost") as secure:
                    return {"verified": True, "tls_version": secure.version(),
                            "peer_certificate_sha256": hashlib.sha256(
                                secure.getpeercert(binary_form=True)).hexdigest()}
        except (OSError, ssl.SSLError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tls-probe", type=Path)
    args = parser.parse_args()
    if args.tls_probe:
        print(json.dumps(tls_probe(args.tls_probe)), flush=True)
        return
    if args.task is None:
        parser.error("--task is required for setup")
    task = args.task.resolve(strict=True)
    output = (args.output or task / "acceptance/auth19").resolve()
    if not output.is_relative_to(task):
        raise RuntimeError("output must belong to the task")
    health = json.loads((task / "cluster/resume18/etcd-health.json").read_text())
    if health["rc"] != 0 or not all(item["health"] for item in json.loads(health["stdout"])):
        raise RuntimeError("etcd recovery health gate has not passed")
    ready = json.loads((task / "cluster/resume18/api-readyz.json").read_text())
    if ready["rc"] != 0 or "[+]etcd ok" not in ready["stdout"]:
        raise RuntimeError("API recovery gate has not passed")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    base = [sys.executable, str(task / "cluster/namespace-lab07.py"),
            "run", "--task", str(task), "--"]
    secret = subprocess.run(base + ["kubectl", "-n", "akernel", "get", "secret",
                                    "akernel-adx-tls", "-o", "json"],
                            text=True, capture_output=True, check=True, timeout=45)
    data = json.loads(secret.stdout)["data"]
    ca = output / "public-server.pem"
    write_private(ca, base64.b64decode(data["public.pem"]).decode())
    token = base64.b64decode(data["admin-key"]).decode()
    env = {"AKERNEL_SERVER_ADDRESS": "localhost:18443",
           "AKERNEL_GATEWAY_ADDRESS": "http://127.0.0.1:18080",
           "AKERNEL_TOKEN": token, "AKERNEL_VERIFY_TLS": "true",
           "SSL_CERT_FILE": str(ca), "REQUESTS_CA_BUNDLE": str(ca),
           "CURL_CA_BUNDLE": str(ca), "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    write_private(output / "sdk.env", "".join(
        "export " + key + "=" + shlex.quote(value) + "\n" for key, value in env.items()))
    group = Path("/sys/fs/cgroup/akernel-pr119-pod-20261022-XfboxUgq/tools")

    def enter_group():
        (group / "cgroup.procs").write_text(str(os.getpid()))

    with (output / "port-forward.stdout").open("xb") as stdout, \
            (output / "port-forward.stderr").open("xb") as stderr:
        process = subprocess.Popen(base + ["kubectl", "-n", "akernel", "port-forward",
                                          "--address=127.0.0.1", "svc/akernel-adx-ingress-api",
                                          "18443:8443", "18080:8080"],
                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   start_new_session=True, preexec_fn=enter_group)
    record = {"port_forward": identity(process.pid), "credentials_private": True,
              "service": "akernel/akernel-adx-ingress-api", "tls_verification_disabled": False}
    write_private(output / "started.json", json.dumps(record, indent=2) + "\n")
    probe = subprocess.run(base + [sys.executable, str(Path(__file__).resolve()),
                                  "--tls-probe", str(ca)],
                           text=True, capture_output=True, timeout=75)
    write_private(output / "tls-probe.json", json.dumps(
        {"rc": probe.returncode, "stdout": probe.stdout, "stderr": probe.stderr}, indent=2) + "\n")
    if probe.returncode or process.poll() is not None:
        raise RuntimeError("private TLS endpoint failed; retain original process identity and logs")
    record["tls"] = json.loads(probe.stdout)
    record["port_forward_alive_now"] = process.poll() is None
    write_private(output / "ready.json", json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()

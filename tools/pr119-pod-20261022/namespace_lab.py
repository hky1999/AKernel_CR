#!/usr/bin/env python3
"""Own a private network/mount lab and bounded cgroups for a remote Kind task."""

import argparse
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time

CG_NAME = "akernel-pr119-pod-20261022-XfboxUgq"


def write_new(path, value):
    with path.open("x") as f:
        f.write(value)


def identity(pid):
    p = Path("/proc") / str(pid)
    stat = (p / "stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "start_ticks": stat[19],
            "net": os.readlink(p / "ns/net"),
            "mnt": os.readlink(p / "ns/mnt")}


def command(argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise RuntimeError(json.dumps({"argv": argv, "rc": p.returncode,
                                      "stderr": p.stderr}))
    return p.stdout


def child_group(group):
    def enter():
        (group / "cgroup.procs").write_text(str(os.getpid()))
    return enter


def lab_env(task, out):
    env = os.environ.copy()
    for key in list(env):
        if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
            del env[key]
    env.update(HOME=str(out / "home"),
               PATH=str(out / "bin") + ":" +
                    str(task / "k8s-inputs/prepared06/bin") + ":/usr/sbin:/usr/bin:/sbin:/bin",
               CONTAINERS_CONF=str(out / "containers.conf"),
               CONTAINERS_REGISTRIES_CONF=str(out / "registries.conf"),
               REGISTRY_AUTH_FILE=str(out / "auth.json"),
               KUBECONFIG=str(out / "kubeconfig"),
               TMPDIR=str(out / "tmp"), XDG_RUNTIME_DIR=str(out / "xdg"),
               KIND_EXPERIMENTAL_PROVIDER="podman", GOMAXPROCS="2")
    return env


def inside(task, out, host_net, host_mnt):
    current = identity(os.getpid())
    if current["net"] == host_net or current["mnt"] == host_mnt:
        raise RuntimeError("refusing setup without new network and mount namespaces")
    original_resolv = Path(os.path.realpath("/etc/resolv.conf"))
    if str(original_resolv).startswith("/run/"):
        target = out / "run" / original_resolv.relative_to("/run")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    command(["mount", "--bind", str(out / "run"), "/run"])
    command(["mount", "--bind", str(out / "tmp"), "/tmp"])
    command(["mount", "--bind", str(out / "resolv.conf"), "/etc/resolv.conf"])
    command(["mount", "-t", "tmpfs", "-o", "size=128m,nosuid,nodev",
             "pr119-lab-shm", "/dev/shm"])
    command(["hostname", "akcr119-lab"])
    command(["ip", "link", "set", "lo", "up"])
    command(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    record = identity(os.getpid())
    record.update({"task": str(task), "status": "keeper_ready",
                   "cgroup": (Path("/proc/self/cgroup")).read_text(),
                   "private_mounts": ["/run", "/tmp", "/etc/resolv.conf", "/dev/shm"],
                   "host_sysctl_writes": 0, "private_net_sysctl_writes": 1})
    write_new(out / "ready.json", json.dumps(record, indent=2))
    while True:
        signal.pause()


def start(task, out):
    if shutil.disk_usage(task).free < 250 * 1024 ** 3:
        raise RuntimeError("disk free below 250 GiB")
    out.mkdir(mode=0o700)
    for name in ("run", "tmp", "home", "bin", "xdg", "graph", "runroot",
                 "libpod-tmp", "networks", "logs"):
        (out / name).mkdir(mode=0o700)
    (out / "tmp").chmod(0o1777)
    write_new(out / "resolv.conf", "nameserver 10.254.239.3\noptions timeout:2 attempts:3\n")
    write_new(out / "auth.json", '{"auths":{}}\n')
    write_new(out / "registries.conf",
              'unqualified-search-registries = ["docker.io"]\nshort-name-mode = "disabled"\n')
    write_new(out / "containers.conf",
              '[containers]\nlog_driver="k8s-file"\npids_limit=8192\ncgroupns="private"\n'
              '[engine]\ncgroup_manager="cgroupfs"\nevents_logger="file"\n'
              '[network]\nnetwork_backend="netavark"\nfirewall_driver="nftables"\n')
    cg = Path("/sys/fs/cgroup") / CG_NAME
    cg.mkdir()
    (cg / "cpu.max").write_text("1200000 100000")
    (cg / "memory.max").write_text(str(40 * 1024 ** 3))
    (cg / "memory.high").write_text(str(36 * 1024 ** 3))
    (cg / "memory.swap.max").write_text("0")
    (cg / "pids.max").write_text("32768")
    allowed = sorted(os.sched_getaffinity(0))[:12]
    (cg / "cpuset.cpus").write_text(",".join(map(str, allowed)))
    (cg / "cpuset.mems").write_text((cg.parent / "cpuset.mems.effective").read_text())
    (cg / "cgroup.subtree_control").write_text("+cpu +memory +pids +cpuset")
    for name in ("keeper", "tools", "nodes"):
        (cg / name).mkdir()
    (cg / "nodes/cgroup.subtree_control").write_text("+cpu +memory +pids +cpuset")
    manifest = {"task": str(task), "out": str(out), "cgroup": str(cg),
                "cgroup_identity": {"device": cg.stat().st_dev, "inode": cg.stat().st_ino},
                "host_namespaces": identity(os.getpid()),
                "cpu_quota": 12, "memory_max_gib": 40, "created_unix": time.time()}
    write_new(out / "owner.json", json.dumps(manifest, indent=2))
    wrapper = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
out=Path(__OUT__)
ready=json.loads((out/"ready.json").read_text())
if os.readlink("/proc/self/ns/net") != ready["net"]:
    raise SystemExit("refusing podman outside task network namespace")
args=sys.argv[1:]
if args and args[0] in ("run","create"):
    if any(x.startswith("--cgroup-parent") for x in args):
        raise SystemExit("caller cgroup-parent override refused")
    args=args[:1]+["--cgroup-parent=/__CG__/nodes","--cpus=4","--memory=10g",
                  "--pids-limit=8192"]+args[1:]
prefix=["/usr/bin/podman","--root",str(out/"graph"),"--runroot",str(out/"runroot"),
        "--tmpdir",str(out/"libpod-tmp"),"--network-config-dir",str(out/"networks"),
        "--storage-driver","overlay","--cgroup-manager","cgroupfs",
        "--events-backend","file"]
os.execv(prefix[0],prefix+args)
""".replace("__OUT__", repr(str(out))).replace("__CG__", CG_NAME)
    write_new(out / "bin/podman", wrapper)
    (out / "bin/podman").chmod(0o700)
    host = manifest["host_namespaces"]
    argv = ["unshare", "--mount", "--net", "--uts", "--ipc", "--propagation", "private",
            "--", sys.executable, str(Path(__file__).absolute()), "inside",
            "--task", str(task), "--lab", out.name,
            "--host-net", host["net"], "--host-mnt", host["mnt"]]
    with (out / "logs/keeper.stdout").open("xb") as so, (out / "logs/keeper.stderr").open("xb") as se:
        keeper = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=so, stderr=se,
                                  start_new_session=True, close_fds=True,
                                  preexec_fn=child_group(cg / "keeper"))
    manifest["keeper"] = identity(keeper.pid)
    write_new(out / "keeper-launch.json", json.dumps(manifest, indent=2))
    for _ in range(100):
        if (out / "ready.json").exists():
            break
        if keeper.poll() is not None:
            raise RuntimeError("keeper exited; preserve logs and do not restart blindly")
        time.sleep(0.1)
    else:
        raise RuntimeError("keeper still starting; inspect the recorded live handle")
    readfd, writefd = os.pipe()
    args = ["slirp4netns", "--configure", "--disable-host-loopback", "--mtu=65520",
            "--cidr=10.254.239.0/24", "--ready-fd=" + str(writefd),
            str(keeper.pid), "tap0"]
    with (out / "logs/slirp.stdout").open("xb") as so, (out / "logs/slirp.stderr").open("xb") as se:
        slirp = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=so, stderr=se,
                                 start_new_session=True, pass_fds=(writefd,),
                                 preexec_fn=child_group(cg / "tools"))
    os.close(writefd)
    manifest["slirp"] = identity(slirp.pid)
    write_new(out / "slirp-launch.json", json.dumps(manifest, indent=2))
    signaled = select.select([readfd], [], [], 15)[0]
    marker = os.read(readfd, 1) if signaled else b""
    os.close(readfd)
    if marker != b"1" or slirp.poll() is not None:
        raise RuntimeError("slirp not confirmed ready; inspect original process and logs")
    manifest["status"] = "private_network_ready_no_cluster"
    write_new(out / "started.json", json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


def run(task, out, argv):
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise RuntimeError("missing command after --")
    ready = json.loads((out / "ready.json").read_text())
    actual = identity(ready["pid"])
    for key in ("pid", "start_ticks", "net", "mnt"):
        if actual[key] != ready[key]:
            raise RuntimeError("keeper identity changed: " + key)
    cg = Path("/sys/fs/cgroup") / CG_NAME
    args = ["nsenter", "--target", str(ready["pid"]), "--mount", "--net", "--uts",
            "--ipc", "--"] + argv
    p = subprocess.run(args, env=lab_env(task, out),
                       preexec_fn=child_group(cg / "tools"))
    raise SystemExit(p.returncode)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("start", "inside", "run"))
    p.add_argument("--task", required=True)
    p.add_argument("--lab", default="lab07")
    p.add_argument("--host-net")
    p.add_argument("--host-mnt")
    a, rest = p.parse_known_args()
    task = Path(a.task)
    if not task.is_absolute() or task.resolve() != task or not task.is_dir():
        p.error("invalid private task")
    if a.lab != "lab07":
        p.error("this fixed experiment only owns lab07")
    out = task / "cluster" / a.lab
    if a.action == "inside":
        inside(task, out, a.host_net, a.host_mnt)
    elif a.action == "start":
        start(task, out)
    else:
        run(task, out, rest)


if __name__ == "__main__":
    main()


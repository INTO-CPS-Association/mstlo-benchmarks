"""Record what produced a set of results, next to the results.

    python3 metadata.py start           # a stage is starting in $RESULTS_DIR
    python3 metadata.py input <name> <path>   # something it read from elsewhere
    python3 metadata.py finish <status>       # how it ended

One metadata.json per result directory: the machine everything ran on, plus one
record per stage that wrote there.  `gather`, `run` and `analyze` append to the
same file in the order they ran, so a directory carries its own history.

Everything comes from the environment the entrypoint has already set up.  The
config file itself is copied in beside this, so `settings` only has to cover the
variables the stage was actually driven by.
"""

import hashlib
import json
import os
import platform
import subprocess
import sys
import tomllib
from datetime import datetime, timezone

METADATA_FILE = "metadata.json"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def clean(value):
    # lscpu prints a bare "-" for fields the guest cannot see, which is worse
    # than nothing: it looks like an answer.
    value = (value or "").strip()
    return value if value and value != "-" else None


def cpu_model():
    """The CPU the numbers came from, as specifically as the container can tell.

    aarch64 Linux emits neither `model name` nor `Model` in /proc/cpuinfo, so
    the obvious lookup returns nothing at all on exactly the machines this image
    is most likely to run on.  `lscpu` knows the part number there.  On a VM --
    Docker Desktop on macOS, say -- even that only reaches the guest's view, so
    an explicit override wins over everything.
    """
    override = clean(os.environ.get("MSTLO_BENCH_HOST_CPU"))
    if override:
        return override

    out = cmd("lscpu") or ""
    for line in out.splitlines():
        if line.startswith("Model name:"):
            if found := clean(line.split(":", 1)[1]):
                return found

    fields = {}
    try:
        for line in open("/proc/cpuinfo"):
            if ":" in line:
                key, _, value = line.partition(":")
                fields.setdefault(key.strip(), value.strip())
    except OSError:
        pass

    for key in ("model name", "Model", "Hardware", "cpu model"):
        if found := clean(fields.get(key)):
            return found

    # aarch64 exposes only the ARM identification registers.  Not a model name,
    # but it does distinguish one core design from another.
    part = clean(fields.get("CPU part"))
    if part:
        implementer = clean(fields.get("CPU implementer")) or "?"
        return f"aarch64 implementer={implementer} part={part}"

    return clean(platform.processor())


def memory_limit_bytes():
    """The container's memory limit, where the platform exposes one."""
    for path in (
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ):
        try:
            with open(path) as f:
                value = f.read().strip()
        except OSError:
            continue
        if not value or value == "max":
            continue
        try:
            parsed = int(value)
        except ValueError:
            continue
        # Some cgroup v1 setups use a very large sentinel for "unlimited".
        return None if parsed >= 1 << 60 else parsed
    return None


def kernel():
    try:
        info = platform.uname()
    except (OSError, RuntimeError):
        return None
    return {
        "system": info.system,
        "release": info.release,
        "version": info.version,
        "machine": info.machine,
    }


def environment():
    """The machine, the image and the toolchain: everything a stage cannot vary."""
    return {
        "container": True,
        # .git is outside the build context, so the revision is passed in.
        "image_version": os.environ.get("MSTLO_BENCH_IMAGE_VERSION"),
        "repository_revision": os.environ.get("MSTLO_BENCH_REPOSITORY_REVISION"),
        "arch": platform.machine() or None,
        "cpu": cpu_model(),
        "cpus": os.cpu_count(),
        "memory_limit_bytes": memory_limit_bytes(),
        "kernel": kernel(),
        "python": platform.python_version(),
        "rustc": cmd("rustc", "--version"),
        # Only the multi-robot benchmark has these; null everywhere else.
        "ros_distribution": os.environ.get("ROS_DISTRO"),
        "ros_middleware": os.environ.get("RMW_IMPLEMENTATION"),
    }


def path():
    return os.path.join(os.environ["RESULTS_DIR"], METADATA_FILE)


def read():
    try:
        with open(path()) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def write(meta):
    with open(path(), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


def settings(config):
    """The variables the stage ran with, overrides included."""
    stage = os.environ["STAGE"]
    keys = {**config.get("common", {}), **config.get(stage, {})}
    return {key: os.environ.get(key) for key in sorted(keys)}


def start():
    with open(os.environ["CONFIG_FILE"], "rb") as f:
        config_bytes = f.read()

    record = {
        "stage": os.environ["STAGE"],
        "config": os.environ["CONFIG"],
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "started_utc": now(),
        "completed_utc": None,
        "status": "running",
        "settings": settings(tomllib.loads(config_bytes.decode())),
        # Filled in by `input` for anything the stage read from another
        # directory: the recording a run replayed, say.
        "inputs": {},
    }

    meta = read() or {"benchmark": os.environ["BENCH"], "environment": environment()}
    meta.setdefault("stages", []).append(record)
    write(meta)


def add_input(name, value):
    meta = read()
    if not meta or not meta.get("stages"):
        return
    meta["stages"][-1]["inputs"][name] = value
    write(meta)


def finish(status):
    meta = read()
    if not meta or not meta.get("stages"):
        return
    meta["stages"][-1]["completed_utc"] = now()
    meta["stages"][-1]["status"] = "ok" if status == "0" else f"failed ({status})"
    write(meta)


if __name__ == "__main__":
    if sys.argv[1] == "start":
        start()
    elif sys.argv[1] == "input":
        add_input(sys.argv[2], sys.argv[3])
    else:
        finish(sys.argv[2])

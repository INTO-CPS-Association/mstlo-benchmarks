"""Record what produced a set of results, next to the results.

    python3 metadata.py start           # before the stage runs
    python3 metadata.py finish <status> # after it, merging in the outcome

Everything comes from the environment the entrypoint has already set up.
"""

import hashlib
import json
import os
import platform
import subprocess
import sys
import tomllib
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def cpu_model():
    """The CPU the numbers came from, as specifically as the container can tell.

    aarch64 Linux emits neither `model name` nor `Model` in /proc/cpuinfo, so
    the obvious lookup returns nothing at all on exactly the machines this image
    is most likely to run on.  `lscpu` knows the part number there.  On a VM --
    Docker Desktop on macOS, say -- even that only reaches the guest's view, so
    an explicit override wins over everything.
    """
    override = os.environ.get("MSTLO_BENCH_HOST_CPU")
    if override:
        return override

    out = cmd("lscpu")
    if out:
        for line in out.splitlines():
            if line.startswith("Model name:"):
                return line.split(":", 1)[1].strip()

    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith(("model name", "Model", "CPU part", "CPU implementer")):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass

    return platform.processor() or None


def path():
    return os.path.join(os.environ["RESULTS_DIR"], "metadata.json")


def start():
    config_bytes = open(os.environ["CONFIG_FILE"], "rb").read()
    config = tomllib.loads(config_bytes.decode())

    meta = {
        "benchmark": os.environ["BENCH"],
        "stage": os.environ["STAGE"],
        "config": os.environ["CONFIG"],
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "started_utc": now(),
        # .git is outside the build context, so the revision is passed in.
        "image_version": os.environ.get("MSTLO_BENCH_IMAGE_VERSION"),
        "repository_revision": os.environ.get("MSTLO_BENCH_REPOSITORY_REVISION"),
        "container": True,
        "arch": platform.machine(),
        "kernel": platform.release(),
        "cpu": cpu_model(),
        "cpus": os.cpu_count(),
        "python": platform.python_version(),
        "rustc": cmd("rustc", "--version"),
        # The values the stage actually ran with, overrides included.
        "settings": {
            key: os.environ.get(key)
            for key in sorted(
                {**config.get("common", {}), **config.get(os.environ["STAGE"], {})}
            )
        },
    }
    with open(path(), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


def finish(status):
    with open(path()) as f:
        meta = json.load(f)
    meta["completed_utc"] = now()
    meta["status"] = "ok" if status == "0" else f"failed ({status})"
    with open(path(), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    if sys.argv[1] == "start":
        start()
    else:
        finish(sys.argv[2])

"""Turn a benchmark's TOML config into shell exports.

The stage scripts are driven by environment variables, so a config is just a
set of them: ``[common]`` merged with the section named after the stage.  A
variable already in the environment is left alone, which is what makes
``docker run -e M_RUNS=7`` override the file.

    eval "$(python3 config.py configs/default.toml run)"
    python3 config.py configs/default.toml run --show   # effective values
"""

import os
import shlex
import sys
import tomllib


def fmt(value):
    if isinstance(value, bool):
        return "1" if value else ""
    return str(value)


def main():
    path, stage = sys.argv[1], sys.argv[2]
    with open(path, "rb") as f:
        cfg = tomllib.load(f)

    merged = {**cfg.get("common", {}), **cfg.get(stage, {})}

    if "--show" in sys.argv:
        for key, value in merged.items():
            print(f"  {key}={os.environ.get(key, fmt(value))}")
    else:
        for key, value in merged.items():
            if key not in os.environ:
                print(f"export {key}={shlex.quote(fmt(value))}")


if __name__ == "__main__":
    main()

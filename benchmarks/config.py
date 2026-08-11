"""Turn a benchmark's TOML config into shell exports.

The stage scripts are driven by environment variables, so a config is just a
set of them: ``[common]`` merged with the section named after the stage.  A
variable already in the environment is left alone, which is what makes
``docker run -e M_RUNS=7`` override the file.  A list becomes one entry per
line, so a setting can hold text that no separator would survive.

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
    if isinstance(value, list):
        # One entry per line.  A list is what a config reaches for when no
        # separator can be picked -- an STL formula contains commas, brackets
        # and spaces -- and a newline is the one thing an entry does not hold.
        return "\n".join(fmt(item) for item in value)
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

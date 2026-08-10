# Course services

The incubator `gather` stage drives two services from the
[IncubatorDTCourse](https://github.com/clagms/IncubatorDTCourse):

- `5-IncubatorPTEmulator/pt_emulator_service.py` — the plant
- `2-Controller-Modelling/controller.py` — the thermostat

Neither is committed to the course repository. Both come from `%%writefile`
cells inside the notebooks, which write them out only when a reader steps
through `0-Pre-requisites` … `6-PuttingItAllTogether` by hand. They are
therefore absent from the `incubator-dt-course/` subtree, and no subtree can
supply them.

Since this repository is meant to work out of the box, they are committed here
instead, extracted verbatim from the notebooks at the pinned course commit
`8dca7629a2480b3726901006f834270afae202b4`:

| file | notebook |
|---|---|
| `5-IncubatorPTEmulator/pt_emulator_service.py` | `5-IncubatorPTEmulator/1-IncubatorPTEmulator.ipynb` |
| `2-Controller-Modelling/controller.py` | `2-Controller-Modelling/2-IncubatorControllerService.ipynb` |

`docker/Dockerfile.mstlo` copies this directory over the course checkout, so the
services land beside the notebooks that define them, exactly where the course
layout expects.

## Refreshing them

If the `incubator-dt-course` subtree is ever updated to a newer commit, these
two files have to be re-extracted from the new notebooks. The cells are plain
JSON, so no Jupyter and no broker is needed:

```python
import json, pathlib

for notebook in sorted(pathlib.Path("incubator-dt-course").glob("*/*.ipynb")):
    for cell in json.loads(notebook.read_text())["cells"]:
        lines = cell["source"]
        if lines and lines[0].startswith("%%writefile "):
            name = lines[0].split(None, 1)[1].strip()
            if name in ("pt_emulator_service.py", "controller.py"):
                target = pathlib.Path("benchmarks/incubator/course-services") \
                    / notebook.parent.name / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("".join(lines[1:]))
                print("wrote", target)
```

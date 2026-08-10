# Course services

The incubator `gather` stage drives two services from the
[IncubatorDTCourse](https://github.com/clagms/IncubatorDTCourse):

- `5-IncubatorPTEmulator/pt_emulator_service.py` — the plant
- `2-Controller-Modelling/controller.py` — the thermostat

Neither is committed to the course repository, so neither can come from the
`incubator-dt-course/` subtree. They are committed here instead, because this
repository is meant to work out of the box.

## Why they are not in the course

**`controller.py`** comes from a `%%writefile` cell in
`2-Controller-Modelling/2-IncubatorControllerService.ipynb`. The cell writes the
file only when a reader steps through the notebook, so the course repository
never contains it. The copy here is that cell, verbatim, at the pinned course
commit `8dca7629a2480b3726901006f834270afae202b4`.

**`pt_emulator_service.py`** is different, and the difference matters. The
notebook's `%%writefile` cell produces an emulator with **no lid support at
all** — the course leaves that as an exercise. From
`5-IncubatorPTEmulator/1-IncubatorPTEmulator.ipynb`:

> Unlike the real incubator, we will have to code the behavior that corresponds
> to opening the lid. We will trigger this behavior using a rabbitmq message
> that the emulator will listen for.

and, in that notebook's *Exercises* section:

> 1. Adjust the incubator emulator service so that the room temperature can be
>    changed during operation, by sending a rabbitmq message to the emulator
>    containing the new room temperature.
> 2. Adjust the incubator emulator service so that one can simulate the opening
>    of the lid, by sending a rabbitmq message to the emulator, much like the
>    heater is turned on. To simulate the opening of the lid, all you need to do
>    is change the `self._G_br` by, e.g., multiplying it by 10. […] To close the
>    lid, revert `self._G_br` to its original value.

The file here is the emulator **with exercises 1 and 2 completed** — the same
one that recorded the dataset the mstlo paper reports. It adds, over the
notebook cell:

| | |
|---|---|
| `ROUTING_KEY_ROOM_TEMP` queue | exercise 1 — room temperature settable at runtime |
| `ROUTING_KEY_LID` queue | exercise 2 — lid opened and closed by message |
| `self._G_br = self._G_br*10 if lid_cmd else self._G_br/10` | exercise 2 — the conductance change the exercise prescribes |
| `"lid_open": self._lid_open` in the published state | so the recording can be labelled by phase |

Exercise 3 (adding measurement noise) is deliberately **not** applied: the
benchmark monitors a clean signal.

`5-IncubatorPTEmulator/logging.conf` comes with it. The exercise-completed
emulator calls `logging.config.fileConfig("logging.conf")` with a relative path,
and `configparser` ignores a file that is not there, so a missing one surfaces
much later as `KeyError: 'formatters'` rather than as a missing file. Note that
it routes the `PTEmulatorService` logger to a file handler with `propagate=0`,
so the emulator's own lines land in `PTEmulatorService.log` beside the service
inside the container, not in `results/incubator/logs/emulator.log`, which
captures its stdout.

This is not optional decoration. `run_experiment.py` publishes on
`routing.key.lid` and reads `fields["lid_open"]` from every state message, so
the stock notebook emulator makes it fail on its first sample with
`KeyError: 'lid_open'`. Nothing else in the course or in the vendored digital
twin implements that contract: the digital twin's `lid_open_server.py` is an
*offline diagnosis* service on a different routing key, which infers when a lid
was opened from recorded data rather than driving a live plant.

## Refreshing them

If `incubator-dt-course` is ever updated, `controller.py` can be re-extracted
from the new notebook — the cells are plain JSON, so no Jupyter and no broker
are needed:

```python
import json, pathlib

for notebook in sorted(pathlib.Path("incubator-dt-course").glob("*/*.ipynb")):
    for cell in json.loads(notebook.read_text())["cells"]:
        lines = cell["source"]
        if lines and lines[0].startswith("%%writefile "):
            name = lines[0].split(None, 1)[1].strip()
            if name == "controller.py":
                target = pathlib.Path("benchmarks/incubator/course-services") \
                    / notebook.parent.name / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("".join(lines[1:]))
                print("wrote", target)
```

`pt_emulator_service.py` cannot be refreshed that way: re-extracting it would
silently discard the two exercises and break `gather`. Port the changes in the
table above onto the new cell by hand instead.

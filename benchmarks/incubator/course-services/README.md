# Course services

The incubator `gather` stage drives two services from the [IncubatorDTCourse](https://github.com/clagms/IncubatorDTCourse):

- `5-IncubatorPTEmulator/pt_emulator_service.py` — the plant
- `2-Controller-Modelling/controller.py` — the thermostat

Neither is committed to the course repository, so neither can come from the `incubator-dt-course/` subtree. They are committed here instead, because this repository is meant to work out of the box.

## Why they are not in the course

**`controller.py`** comes from a `%%writefile` cell in `2-Controller-Modelling/2-IncubatorControllerService.ipynb`. The cell writes the file only when a reader steps through the notebook, so the course repository never contains it. The copy here is that cell, verbatim, at the pinned course commit `8dca7629a2480b3726901006f834270afae202b4`.

**`pt_emulator_service.py`** is slightly different. The notebook's `%%writefile` cell produces an emulator with **no lid support at all** — the course leaves that as an exercise.

The file here is the emulator **with exercises 1 and 2 completed** . It adds, over the notebook cell:

| | |
|---|---|
| `ROUTING_KEY_ROOM_TEMP` queue | exercise 1 — room temperature settable at runtime |
| `ROUTING_KEY_LID` queue | exercise 2 — lid opened and closed by message |
| `self._G_br = self._G_br*10 if lid_cmd else self._G_br/10` | exercise 2 — the conductance change the exercise prescribes |
| `"lid_open": self._lid_open` in the published state | so the recording can be labelled by phase |

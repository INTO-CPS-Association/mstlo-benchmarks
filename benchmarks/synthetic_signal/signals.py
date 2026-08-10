"""Generate a signal for the run to be measured against.

Five shapes, all written as `timestep,value` CSV and all sampled at
--sampling-rate.  The default 1.0 Hz gives integer timesteps 0, 1, 2, ..., which
is what makes a bound such as `G[0,1000]` mean the same number of steps to every
monitor: mstlo measures its bounds in seconds, RTAMT counts samples.

sine and chirp are upstream's, unchanged -- signal_generation/signal_generator.py
in the mstlo checkout produces the same file for the same arguments, which
tests/test_signals.py pins.  The two ramps and the constant are new, and are
here to ask what a monitor costs on a signal that never oscillates: the sweep is
about the temporal depth of a formula, and a shape that keeps every subformula's
verdict settled separates the cost of remembering from the cost of deciding.
"""

import argparse
import csv
from pathlib import Path

import numpy as np

# What --signal-type accepts.  The shape parameters are per type -- a chirp has
# no amplitude, a constant has no frequency -- so a stage script passes all of
# them and each shape takes the ones it has a use for.
SIGNAL_TYPES = ("sine", "chirp", "linear-increasing", "linear-decreasing", "constant")


def timesteps(num_samples: int, sampling_rate: float) -> np.ndarray:
    return np.arange(num_samples, dtype=float) / sampling_rate


def sine(t: np.ndarray, frequency: float) -> np.ndarray:
    return np.sin(2 * np.pi * frequency * t)


def chirp(t: np.ndarray, duration: float, start_frequency: float, end_frequency: float) -> np.ndarray:
    """A sine whose frequency sweeps linearly from start to end over the signal.

    The sweep ends at *duration*, one sample past the last one, which is where
    upstream puts it: t1 comes from the sample count and the rate, not t[-1].
    """
    from scipy.signal import chirp as scipy_chirp

    if t.size == 0:
        return np.array([], dtype=float)
    return scipy_chirp(t, f0=start_frequency, f1=end_frequency, t1=duration, method="linear")


def ramp(t: np.ndarray, start_value: float, end_value: float) -> np.ndarray:
    """A straight line from start_value to end_value across the whole signal."""
    if t.size < 2:
        return np.full(t.size, start_value, dtype=float)
    return np.linspace(start_value, end_value, t.size)


def constant(t: np.ndarray, value: float) -> np.ndarray:
    return np.full(t.size, value, dtype=float)


def generate(
    signal_type: str,
    num_samples: int,
    sampling_rate: float,
    frequency: float,
    start_frequency: float,
    end_frequency: float,
    amplitude: float,
    value: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (timesteps, values) for one of SIGNAL_TYPES."""
    t = timesteps(num_samples, sampling_rate)

    if signal_type == "sine":
        return t, sine(t, frequency)
    if signal_type == "chirp":
        return t, chirp(t, num_samples / sampling_rate, start_frequency, end_frequency)
    # The ramps differ only in direction, so one amplitude describes both: the
    # signal crosses every threshold the built-in formulas test exactly once.
    if signal_type == "linear-increasing":
        return t, ramp(t, -amplitude, amplitude)
    if signal_type == "linear-decreasing":
        return t, ramp(t, amplitude, -amplitude)
    if signal_type == "constant":
        return t, constant(t, value)

    raise SystemExit(f"unknown signal type '{signal_type}'; expected one of {', '.join(SIGNAL_TYPES)}")


def write(path: Path, t: np.ndarray, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestep", "value"])
        writer.writerows(zip(t, values))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True, help="output CSV path")
    parser.add_argument("--num-samples", type=int, required=True, help="samples to generate")
    parser.add_argument("--signal-type", choices=SIGNAL_TYPES, default="chirp")
    parser.add_argument("--sampling-rate", type=float, default=1.0, help="Hz")
    parser.add_argument("--frequency", type=float, default=0.01, help="sine frequency in Hz")
    parser.add_argument("--start-frequency", type=float, default=0.01, help="chirp start frequency in Hz")
    parser.add_argument("--end-frequency", type=float, default=0.0001, help="chirp end frequency in Hz")
    parser.add_argument("--amplitude", type=float, default=1.0, help="what the ramps run between")
    parser.add_argument("--value", type=float, default=0.25, help="what the constant holds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.num_samples < 0:
        raise SystemExit("--num-samples must be >= 0")

    t, values = generate(
        signal_type=args.signal_type,
        num_samples=args.num_samples,
        sampling_rate=args.sampling_rate,
        frequency=args.frequency,
        start_frequency=args.start_frequency,
        end_frequency=args.end_frequency,
        amplitude=args.amplitude,
        value=args.value,
    )
    write(Path(args.output), t, values)
    print(f"{args.signal_type} signal with {args.num_samples} samples -> {args.output}")


if __name__ == "__main__":
    main()

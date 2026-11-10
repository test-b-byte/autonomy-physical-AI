#!/usr/bin/env python3
"""
Pi sensor check: is each sensor LIVE (real hardware) or STUB, and what does
it read right now?  Talks to no core: safe to run any time.

  python3 bench/sensor_check.py
  GHOST_FRAMES=tcp://<jetson-ip>:5555 python3 bench/sensor_check.py      # vision via the Jetson camera
  python3 bench/sensor_check.py --label 1.0m --csv bench_1m.csv          # log a distance test

For the distance test: a person stands at 0.5 / 1 / 2 / 3 m in front of the
sensors, about 20 s each, with --label set to the distance. Afterwards, compare
the hit rate per distance with sensors/indoor_specs.json.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sensors"))


def load():
    out = {}
    for name, mod, cls in [("imu", "imu", "IMUSensor"), ("thermal", "thermal", "ThermalSensor"),
                           ("vision", "vision", "VisionSensor"), ("acoustic", "acoustic", "AcousticSensor"),
                           ("ir", "ir", "IRSensor")]:
        try:
            out[name] = getattr(__import__(mod), cls)()
        except Exception as exc:
            print(f"  {name:9} FAILED to start: {exc}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--hz", type=float, default=1.0)
    ap.add_argument("--label", default="", help="tag rows, e.g. the test distance")
    ap.add_argument("--csv", default=None, help="append readings to this CSV")
    args = ap.parse_args()

    sensors = load()
    print("\n  sensor     mode")
    for n, s in sensors.items():
        print(f"  {n:9}  {'LIVE' if getattr(s, '_hw', False) else 'STUB (no hardware — excluded from real searches)'}")
    print()

    writer = None
    if args.csv:
        f = open(args.csv, "a", newline="")
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(["t", "label", "sensor", "live", "detection", "confidence", "extra"])

    hits = {n: [0, 0] for n in sensors}
    try:
        while True:
            row = []
            for n, s in sensors.items():
                live = getattr(s, "_hw", False)
                r = s.read()
                if n == "imu":
                    extra = f"az={r.az:5.2f} gz={r.gz:+.2f}"
                    row.append(f"imu {'L' if live else 's'} {extra}")
                    det, conf = "", ""
                else:
                    valid = getattr(r, "valid", True)
                    det, conf = (r.detection, round(r.confidence, 2)) if valid else ("-", "-")
                    if valid:
                        hits[n][0] += int(r.detection); hits[n][1] += 1
                    rate = f"{100 * hits[n][0] / hits[n][1]:3.0f}%" if hits[n][1] else "  -"
                    extra = f"rate={rate}"
                    row.append(f"{n} {'L' if live else 's'} {'HIT ' if det is True else 'miss' if det is False else ' -- '} {conf!s:>4} {rate}")
                if writer:
                    writer.writerow([round(time.time(), 2), args.label, n, live, det, conf, extra])
            print("  " + " | ".join(row), flush=True)
            time.sleep(1.0 / args.hz)
    except KeyboardInterrupt:
        print("\n  hit rates:", {n: f"{100 * h / t:.0f}% of {t}" for n, (h, t) in hits.items() if t})


if __name__ == "__main__":
    main()

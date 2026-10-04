"""Check the microphone by hand: lists the microphones, then shows a live level meter.

    python scripts/check_microphone.py              # default microphone, 10 seconds
    python scripts/check_microphone.py --device 1 --seconds 5

Speak while it runs; the bar should move. Nothing is saved.
"""

from __future__ import annotations

import argparse
import time

from clinassist.adapters.recorder import RecorderError, SoundDeviceRecorder, list_input_devices


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", type=int, default=None, help="index from the list")
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args(argv)

    print("Microphones:")
    for d in list_input_devices():
        print(f"  [{d.index}] {d.name}")

    rec = SoundDeviceRecorder(device=args.device)
    try:
        rec.start()
    except RecorderError as exc:
        print(f"Could not start: {exc.code}")
        return 1
    print(f"\nRecording for {args.seconds:.0f} s. Speak now.\n")
    end = time.monotonic() + args.seconds
    while time.monotonic() < end:
        bar = "#" * int(min(rec.level * 4, 1.0) * 50)  # x4 so normal speech fills the bar
        print(f"\r  {rec.seconds:5.1f} s  |{bar:<50}|", end="", flush=True)
        time.sleep(0.1)
    rec.stop()
    info = rec.last_info
    print(f"\n\nCaptured {info.seconds:.1f} s, peak {info.peak:.3f}, average {info.rms:.4f}")
    if info.silent:
        print("Nothing was heard. Check Settings > Privacy & security > Microphone,")
        print("and that 'Let desktop apps access your microphone' is on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

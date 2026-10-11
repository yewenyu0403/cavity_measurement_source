"""Compatibility entry point. Implementation: src/cavity_measurement/."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from cavity_measurement.measurement import *  # Preserve the existing Python API.

if __name__ == "__main__":
    raise SystemExit(main())

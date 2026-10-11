"""Cavity contour and planar measurement implementation."""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_DEPENDENCIES = PROJECT_ROOT / "_deps"
if PRIVATE_DEPENDENCIES.is_dir():
    sys.path.insert(0, str(PRIVATE_DEPENDENCIES))

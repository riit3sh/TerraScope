"""Make the shared integration helpers importable from sibling test modules."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

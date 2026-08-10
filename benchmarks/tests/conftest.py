import sys
from pathlib import Path

# The shared stage layer is a set of plain scripts rather than a package: the
# two images copy it in beside the stage scripts, so it is imported by path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

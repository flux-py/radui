"""Main entry point for running RADUI as a module: python -m radui."""

from __future__ import annotations

import sys
from radui.cli import main

if __name__ == "__main__":
    sys.exit(main())

"""Allow ``python -m results_library build ...`` as well as ``...cli``."""

from results_library.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

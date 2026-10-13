#!/usr/bin/env python3
"""Keep the old recorder entry point passive; all Live actions belong to the UI."""

# Support both direct script execution and imports through the tooling package.
if __package__:
    from .record_demo_live import main
else:
    from record_demo_live import main


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FILES = [
    "test_event_engine.py",
    "test_event_discovery.py",
    "test_journey_intelligence.py",
    "test_live_transport.py",
    "test_parking_intelligence.py",
    "test_platform.py",
    "test_api.py",
]


def main():
    failed = []
    for name in FILES:
        path = ROOT / name
        print("==>", name)
        try:
            runpy.run_path(str(path), run_name="__main__")
        except SystemExit as error:
            if error.code:
                failed.append(name)
        except Exception as error:
            print("FAIL", name, error)
            failed.append(name)
    if failed:
        raise SystemExit(f"Failed: {', '.join(failed)}")
    print("All test modules passed")


if __name__ == "__main__":
    main()

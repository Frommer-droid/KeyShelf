import sys

from app.core.application import main

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--runtime-smoke-test":
        from app.core.runtime_smoke import check
        raise SystemExit(check(sys.argv[2]))
    raise SystemExit(main())

from deezy.__main__ import main

if __name__ == "__main__":
    # Delegate to the package entrypoint which handles consistent
    # initialization (including stdout/stderr buffering) so both
    # `python deezy.py` and `python -m deezy` behave the same.
    raise SystemExit(main())

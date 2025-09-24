import sys

from deezy.cli import cli_parser


def main() -> int:
    """Entry point wrapper so the package is runnable via `python -m deezy`.

    Delegates to the CLI entry in the `cli` package which defines the actual
    argument parsing and command dispatch.
    """
    try:
        # Ensure line-buffered stdout/stderr with UTF-8 encoding so stdout/stderr
        # behave consistently when DeeZy is invoked by wrapper tools.
        try:
            # some environments (IDEs, redirected streams) might not support
            # fileno() or reopening; guard against that to avoid crashing the
            # entire CLI startup.
            sys.stdout = open(sys.stdout.fileno(), "w", 1, encoding="utf-8")
            sys.stderr = open(sys.stderr.fileno(), "w", 1, encoding="utf-8")
        except Exception:
            # if we can't re-open the streams, continue without modification.
            pass

        # The CLI package exposes `cli_parser()` as the entrypoint that sets up
        # argparse and dispatches commands. Call it and translate any
        # SystemExit into an int return code for the module runner.
        try:
            cli_parser()
            return 0
        except SystemExit as se:
            # Normalize SystemExit codes to an int (None -> 0)
            code = se.code
            if code is None:
                return 0
            try:
                return int(code)
            except Exception:
                return 1
    except Exception as e:  # pragma: no cover - simple bootstrap wrapper
        # If something goes wrong at import time, print a helpful message and
        # re-raise so errors are visible to the user.
        print(f"Failed to start DeeZy CLI: {e}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())

import logging

logger = logging.getLogger("deezy")


def init_logger(level: int | str = logging.INFO) -> None:
    """Use at entry point to configure the logger."""
    logging.basicConfig(level=level, format="%(message)s")

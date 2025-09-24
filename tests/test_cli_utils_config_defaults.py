import argparse

from deezy.cli.utils import apply_config_defaults_to_args


class DummyConfig:
    def __init__(self, mapping):
        self._m = mapping

    def get_config_default(self, key):
        return self._m.get(key)


class RaisingConfig:
    def get_config_default(self, _key):
        raise RuntimeError("boom")


def test_limits_and_jitter_and_bool_override():
    args = argparse.Namespace(
        limit_ffmpeg=5,
        limit_dee=None,
        limit_truehdd=None,
        jitter_ms=0,
        overwrite=False,
        parse_elementary_delay=False,
        log_to_file=False,
        no_progress_bars=False,
    )

    cfg = DummyConfig(
        {
            "limit_dee": "0",  # 0 means inherit -> None
            "limit_truehdd": "2",
            "jitter_ms": "20",
            "overwrite": True,
        }
    )

    ff, de, th = apply_config_defaults_to_args(args, cfg)

    assert ff == 5  # CLI overrides config
    assert de is None  # config 0 -> inherit
    assert th == 2
    assert args.jitter_ms == 20
    assert args.overwrite is True


def test_missing_attrs_and_string_boolean_values():
    # args missing many attributes; helper should create/modify them as needed
    args = argparse.Namespace()
    cfg = DummyConfig(
        {
            "limit_ffmpeg": "0",
            "limit_dee": "3",
            "limit_truehdd": None,
            "jitter_ms": "15",
            "overwrite": "1",
            "no_progress_bars": 0,
        }
    )

    ff, de, th = apply_config_defaults_to_args(args, cfg)

    assert ff is None
    assert de == 3
    assert th is None
    # jitter should be set from config
    assert getattr(args, "jitter_ms") == 15
    # string/number truthy values should become booleans
    assert getattr(args, "overwrite") is True
    assert getattr(args, "no_progress_bars") is False


def test_config_exception_does_not_break():
    args = argparse.Namespace(jitter_ms=0)
    cfg = RaisingConfig()

    ff, de, th = apply_config_defaults_to_args(args, cfg)

    # on exception the function should return None limits and leave jitter unchanged
    assert ff is None and de is None and th is None
    assert args.jitter_ms == 0

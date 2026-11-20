from pathlib import Path

import pytest

from .harness import Tools, make_damf, truehd_stream


def pytest_collection_modifyitems(items):
    here = Path(__file__).parent
    for item in items:
        if here in Path(item.fspath).parents:
            item.add_marker(pytest.mark.dee)


@pytest.fixture(scope="session")
def tools() -> Tools:
    found = Tools.from_env()
    if found is None:
        pytest.skip("set DEEZY_DEE_DIR (and ffmpeg on PATH or DEEZY_FFMPEG)")
    missing = [
        name
        for name in ("dee_ddp_encoder", "dee_ddpjoc_encoder", "dee_dthd_encoder")
        if not found.tool(name).is_file()
    ]
    if missing:
        pytest.skip(f"DEEZY_DEE_DIR lacks {', '.join(missing)}")
    return found


@pytest.fixture(scope="session")
def work(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("dee")


@pytest.fixture(scope="session")
def shim(tools) -> Tools:
    if not tools.shim:
        pytest.skip("set DEEZY_SHIM for the dee_shim tests")
    return tools


@pytest.fixture(scope="session")
def thd(tools, work) -> Path:
    if not tools.atmos_sample or not tools.truehdd:
        pytest.skip("set DEEZY_ATMOS_SAMPLE and DEEZY_TRUEHDD for the Atmos tests")
    return truehd_stream(tools, work)


@pytest.fixture(scope="session")
def damf(tools, work, thd) -> Path:
    """A DAMF master decoded from the sample, with no warp mode forced."""
    return make_damf(tools, thd, work / "damf")

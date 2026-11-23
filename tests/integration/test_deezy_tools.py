"""`deezy tools` with the real tools: every version is read."""

from deezy.cli.tools_report import tool_lines, tool_rows
from deezy.dee.shim import MIN_SHIM_VERSION, parse_version


def test_the_real_tools_report_their_versions(tools, tmp_path):
    rows = {
        row.name: row
        for row in tool_rows(
            tmp_path,
            ffmpeg=tools.ffmpeg,
            truehdd=tools.truehdd,
            dee=str(tools.dee_dir),
            dee_shim=tools.shim,
        )
    }
    assert rows["ffmpeg"].ok and rows["ffmpeg"].version
    assert rows["DEE"].ok and rows["DEE"].version.startswith("6.7.")
    if tools.truehdd:
        assert parse_version(rows["truehdd"].version or "")
    if tools.shim:
        assert parse_version(rows["dee_shim"].version or "") >= MIN_SHIM_VERSION
        assert not rows["dee_shim"].note
    assert len(tool_lines(list(rows.values()))) >= 8

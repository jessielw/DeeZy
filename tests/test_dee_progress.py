from deezy.audio_processors.dee import (
    _parse_dee_execution_summary,
    _process_dee_progress_line,
)
from deezy.utils.progress import DEEProgressHandler


def make_state() -> dict:
    return {
        "measure_done": False,
        "last_measure": 0.0,
        "last_encode": 0.0,
        "encode_task_id": None,
        "measure_task_id": None,
        "progress": None,
        "encode_start_value": None,
    }


def encode_line(value: float) -> str:
    return (
        "INFO: framework: Stage: audio filter, Stage name: pcm_to_ddp, "
        f"Step: encoding, Stage progress: {value}, Overall progress: {value}."
    )


def test_encode_finishing_within_one_progress_interval(capsys):
    """DEE's first encode line can already read 100 on a short or heavily loaded
    encode, which used to divide by a zero-width span."""
    handler = DEEProgressHandler(20, True, None, 0)
    state = make_state()

    _process_dee_progress_line(encode_line(100.0), handler, state)

    assert state["encode_start_value"] == 100.0
    assert state["last_encode"] == 100.0


def test_encode_progress_is_rescaled_from_its_starting_point(capsys):
    handler = DEEProgressHandler(20, True, None, 0)
    state = make_state()

    # DEE reports encode progress on the same 0-100 scale it used for measuring,
    # so a run that starts encoding at 50 has to be stretched back out to 0-100
    _process_dee_progress_line(encode_line(50.0), handler, state)
    _process_dee_progress_line(encode_line(75.0), handler, state)

    assert state["last_encode"] == 50.0


def percent_handler() -> DEEProgressHandler:
    return DEEProgressHandler(20, True, None, 0, percent_progress=True)


BAR = "[====================>                   ] {} %"


def test_measure_percentages_are_stretched_over_the_whole_bar():
    """The split encoders draw one 0-100 bar across both steps, so measuring
    (step 1 of 2) only ever reaches 50."""
    handler = percent_handler()

    handler.parse_dee_line("[11:54:01.906] Step 1/2 : Loudness Measurement")
    data, is_encode = handler.parse_dee_line(BAR.format(25))

    assert data is not None and data.value == 50.0
    assert not is_encode


def test_encode_step_line_switches_to_encode_progress():
    handler = percent_handler()

    handler.parse_dee_line("Step 1/2 : Loudness Measurement")
    handler.parse_dee_line(BAR.format(50))
    assert handler.parse_dee_line("[11:54:09.313] Step 2/2 : Encoding") == (None, False)
    data, is_encode = handler.parse_dee_line(BAR.format(75))

    # encode values are left as reported; the caller rescales from where they began
    assert data is not None and data.value == 75.0
    assert is_encode


def test_split_encoder_job_reports_measure_then_encode():
    handler = percent_handler()
    state = make_state()

    for line in (
        "Step 1/2 : Loudness Measurement",
        BAR.format(25),
        BAR.format(50),
        "Step 2/2 : Encoding",
        BAR.format(50),
        BAR.format(75),
    ):
        _process_dee_progress_line(line, handler, state)

    assert state["last_measure"] == 100.0
    assert state["encode_start_value"] == 50.0
    assert state["last_encode"] == 50.0


def test_a_bar_redrawn_at_the_same_value_is_reported_once():
    handler = percent_handler()

    assert handler.parse_dee_line(BAR.format(10))[0] is not None
    assert handler.parse_dee_line(BAR.format(10))[0] is None
    assert handler.parse_dee_line(BAR.format(11))[0] is not None


def test_lines_without_a_percentage_are_ignored_for_split_encoders():
    handler = percent_handler()

    assert handler.parse_dee_line("[11:54:01.906] measured_loudness=-24.1")[0] is None
    assert handler.parse_dee_line("Stage progress: 50.0")[0] is None


def test_single_dee_ignores_bare_percentages():
    handler = DEEProgressHandler(20, True, None, 0)

    assert handler.parse_dee_line("copied 50% of the file")[0] is None


def test_split_encoder_measured_loudness_is_still_collected():
    handler = percent_handler()

    handler.parse_dee_line("[11:54:01.906] measured_loudness=-24.1.")

    assert handler.get_formatted_dialnorm() == "(-24.10 dB)"


def test_split_encoder_errors_are_summarised():
    lines = [
        '[2026-11-06 11:54:01.906] ERROR: File "x.lic" does not exist.',
        "",
        "---- Summary of errors and warnings ----",
        'ERROR: File "x.lic" does not exist.',
        "----------------------------------------",
        "Execution time: 0.0012106 seconds",
    ]

    message = _parse_dee_execution_summary(lines)

    assert message is not None
    assert 'ERROR: File "x.lic" does not exist.' in message
    assert "Execution time: 0.0012106 seconds" in message


def test_single_dee_errors_are_still_summarised():
    lines = [
        "--- Execution summary starts here ---",
        "ERROR: bad job",
        "Time elapsed: 0.1 seconds",
    ]

    assert "ERROR: bad job" in (_parse_dee_execution_summary(lines) or "")


def test_dee_output_that_is_not_text_does_not_abort_the_job():
    """The split encoders print stray bytes in their license line, which used to
    raise a UnicodeDecodeError on Windows' default codepage."""
    import sys

    from deezy.audio_processors.dee import process_dee_job

    # 0x90 and 0x81 are undefined in cp1252; 10 is the newline ending the line
    script = (
        "import sys; sys.stdout.buffer.write(bytes([0x90, 0x81, 10])); "
        "sys.stdout.flush()"
    )

    assert process_dee_job(
        [sys.executable, "-c", script, "--loglevel", "info"], no_progress_bars=True
    )

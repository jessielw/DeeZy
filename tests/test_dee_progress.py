from deezy.audio_processors.dee import _process_dee_progress_line
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

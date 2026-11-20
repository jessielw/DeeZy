import threading
import time

from deezy.pipeline import run


def _hold_slot(tool, hold_time, seen_counter, seen_max, lock):
    with run.slot(tool):
        with lock:
            seen_counter[0] += 1
            seen_max[0] = max(seen_max[0], seen_counter[0])
        time.sleep(hold_time)
        with lock:
            seen_counter[0] -= 1


def most_at_once(tool: str, workers: int) -> int:
    seen_counter, seen_max, lock = [0], [0], threading.Lock()
    threads = [
        threading.Thread(
            target=_hold_slot, args=(tool, 0.05, seen_counter, seen_max, lock)
        )
        for _ in range(workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=1)
    return seen_max[0]


def test_limits_default_to_max_parallel():
    run.init_phase_limits(max_parallel=3, jitter_ms=10)
    assert most_at_once("ffmpeg", 3) == 3
    assert most_at_once("dee", 3) == 3


def test_a_lower_limit_holds_back_the_rest():
    run.init_phase_limits(max_parallel=3, jitter_ms=0, dee_limit=1)
    assert most_at_once("dee", 3) == 1


def test_a_limit_above_max_parallel_is_capped():
    run.init_phase_limits(max_parallel=2, jitter_ms=0, ffmpeg_limit=5)
    assert most_at_once("ffmpeg", 4) == 2

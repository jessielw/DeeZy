import threading
import time

from deezy.audio_encoders.dee.base import BaseDeeAudioEncoder
from deezy.payloads.shared import ChannelBitrates
from tests.utils.payload_helpers import generate_dummy_core_payload


class DummyEncoder(BaseDeeAudioEncoder):
    """Minimal concrete encoder used for semaphore tests."""

    @staticmethod
    def _get_channel_bitrate_object(
        desired_channels=None, source_channels: int = 0
    ) -> ChannelBitrates:
        return ChannelBitrates(default=0, choices=(0,))

    @staticmethod
    def _get_down_mix_config(*args, **kwargs) -> str:
        return ""

    def _generate_ffmpeg_cmd(self, *args, **kwargs) -> list[str]:
        return []


def _run_acquire_release(
    acquire_fn, release_fn, hold_time, seen_counter, seen_max, lock
):
    acquire_fn()
    try:
        with lock:
            seen_counter[0] += 1
            if seen_counter[0] > seen_max[0]:
                seen_max[0] = seen_counter[0]
        time.sleep(hold_time)
    finally:
        with lock:
            seen_counter[0] -= 1
        release_fn()


def test_phase_semaphores_limits():
    # initialize with 3 parallel workers and small jitter
    BaseDeeAudioEncoder.init_phase_limits(max_parallel=3, jitter_ms=10)

    # FFmpeg semaphore should allow up to max_parallel acquisitions
    seen_counter = [0]
    seen_max = [0]
    lock = threading.Lock()
    threads = []
    for _ in range(3):
        t = threading.Thread(
            target=_run_acquire_release,
            args=(
                DummyEncoder(generate_dummy_core_payload())._acquire_ffmpeg,
                DummyEncoder(generate_dummy_core_payload())._release_ffmpeg,
                0.05,
                seen_counter,
                seen_max,
                lock,
            ),
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=1)

    assert seen_max[0] == 3, "FFmpeg semaphore should allow 3 concurrent acquisitions"

    # DEE semaphore defaults to max_parallel, so for 3 -> 3
    seen_counter = [0]
    seen_max = [0]
    lock = threading.Lock()
    threads = []
    for _ in range(3):
        t = threading.Thread(
            target=_run_acquire_release,
            args=(
                DummyEncoder(generate_dummy_core_payload())._acquire_dee,
                DummyEncoder(generate_dummy_core_payload())._release_dee,
                0.05,
                seen_counter,
                seen_max,
                lock,
            ),
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=1)

    assert seen_max[0] == 3, (
        "DEE semaphore should allow 3 concurrent acquisitions for max_parallel=3"
    )

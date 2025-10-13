from deezy.payloads.shared import CorePayload


def generate_dummy_core_payload() -> CorePayload:
    """Generates a dummy core payload to appease tests."""
    return type(
        "TestPayload",
        (),
        {
            k: getattr(CorePayload, k).default
            if hasattr(getattr(CorePayload, k), "default")
            else None
            for k in CorePayload.__annotations__
        },
    )()  # type: ignore[assignment]

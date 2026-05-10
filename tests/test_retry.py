import asyncio
from unittest.mock import patch

from selfheal import retry_async, retry_sync


def test_retry_sync_succeeds_after_retry():
    attempts = 0

    @retry_sync(max_attempts=3, base_delay=0.1, max_delay=1.0)
    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")
        return "ok"

    with patch("time.sleep") as mock_sleep:
        assert flaky() == "ok"

    assert attempts == 2
    mock_sleep.assert_called_once_with(0.1)


def test_retry_sync_raises_after_exhaustion():
    attempts = 0

    @retry_sync(max_attempts=3, base_delay=0.1, max_delay=0.15)
    def always_fails():
        nonlocal attempts
        attempts += 1
        raise RuntimeError("permanent")

    with patch("time.sleep") as mock_sleep:
        try:
            always_fails()
        except RuntimeError as exc:
            assert str(exc) == "permanent"
        else:
            raise AssertionError("always_fails did not raise")

    assert attempts == 3
    assert [call.args[0] for call in mock_sleep.call_args_list] == [0.1, 0.15]


def test_retry_async_succeeds_after_retry():
    attempts = 0

    @retry_async(max_attempts=3, base_delay=0.1, max_delay=1.0)
    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")
        return "ok"

    async def run_test():
        with patch("asyncio.sleep") as mock_sleep:
            assert await flaky() == "ok"
        assert attempts == 2
        mock_sleep.assert_called_once_with(0.1)

    asyncio.run(run_test())

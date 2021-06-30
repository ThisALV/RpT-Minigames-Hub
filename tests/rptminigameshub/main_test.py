from rptminigameshub.__main__ import *
import rptminigameshub.__main__
import asyncio
import pytest


class TestMain:
    """Unit tests for program entry point."""

    @pytest.fixture
    @pytest.mark.asyncio
    def reset_stop_required(self, mocker, event_loop):
        """Resets stop_required to a new instance running on the next async unit test event's loop to emulates a new server run."""

        # New Event() instance will run on current loop generated using event_loop and pytest.mark.asyncio to avoid RuntimeError at wait() return
        mocker.patch.object(rptminigameshub.__main__, "stop_required", asyncio.Event())

    def test_require_stop(self, mocker):
        mocked_print = mocker.patch("builtins.print")
        mocked_event_set = mocker.patch("asyncio.Event.set")

        require_stop()

        mocked_print.assert_called_once_with("\b\b", end="")  # Should have erased the ^C trace inside console
        mocked_event_set.assert_called_once()  # Should have trigger the event that run_until_stopped() is awaiting for

    @pytest.mark.asyncio
    async def test_run_until_stopped(self, mocker, reset_stop_required):
        async def updater_task_mock():  # Mocks the whole servers checkout process, here we just wait a cancel() callable method
            pass

        updater_task = asyncio.create_task(updater_task_mock())

        # Keeps the current method implement but spies it, on a specific object to keep the self argument working
        mocked_event_wait = mocker.patch.object(rptminigameshub.__main__.stop_required, "wait", wraps=rptminigameshub.__main__.stop_required.wait)
        mocked_updater_task_cancel = mocker.patch.object(updater_task, "cancel")

        # Will run in concurrency with run_until_stopped to check for this coroutine to be awaiting Event stop_required
        async def assert_awaiting_then_set():
            await asyncio.sleep(0)  # Ensures run_until_stopped await statement is reach before continuing this coroutine exec
            mocked_event_wait.assert_called_once()  # Should be waiting for the stop_required event
            mocked_updater_task_cancel.assert_not_called()  # Should not have been stopped, expects updater to not have been cancelled yet

            rptminigameshub.__main__.stop_required.set()  # Then, finally fires stop_required so run_until_stopped will no longer be awaiting

        await asyncio.gather(  # Will run assert_awaiting_then_set() while run_until_stopped() is awaiting, then run that last one
            asyncio.create_task(run_until_stopped(updater_task)),
            asyncio.create_task(assert_awaiting_then_set())
        )

        assert rptminigameshub.__main__.stop_required.is_set()  # Should have been finally set because run_until_stopped() returned
        mocked_updater_task_cancel.assert_called_once()  # run_until_stopped() should have cancelled checkouts when server is stopped

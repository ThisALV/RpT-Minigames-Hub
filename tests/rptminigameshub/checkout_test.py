from rptminigameshub.checkout import *
import rptminigameshub.checkout
import pytest
import unittest.mock
import asyncio


class TestSubject:
    """Unit tests for Subject methods."""

    @pytest.mark.asyncio
    async def test_ctor(self):
        subject = Subject()  # Calls class ctor

        assert subject.get_current() is None  # There isn't any value which has been pushed yet
        with pytest.raises(asyncio.InvalidStateError):
            subject.awaitable.result()  # Should throws error as no value is pushed on initial state

    @pytest.mark.asyncio
    async def test_next(self):
        subject = Subject()
        subject.next(0)  # Pushes a value into subject

        assert subject.get_current() == 0  # Our current value (the most updated value which was pushed) should be that value we just pushed
        with pytest.raises(asyncio.InvalidStateError):
            subject.next(1)  # Should throws as current value hasn't been polled yes and is still inside the subject future

    @pytest.mark.asyncio
    async def test_get_next_finished(self):
        subject = Subject()

        async def push_new_value():
            await asyncio.sleep(0)  # Gives priority to the another coroutine so we ensure it is awaiting when we pushes the new value
            subject.next(0)  # Pushes a new value into the subject

        async def wait_new_value():
            polled_value = await subject.get_next()  # Waits for the other coroutine to push its value into the subject
            assert polled_value == 0  # This should be the value pushed by the other coroutine (push_new_value)

        # Pushes a value into the subject and test if it is polled as expected
        await asyncio.gather(asyncio.create_task(push_new_value()), asyncio.create_task(wait_new_value()))

        subject.next(1)  # We should now be able to push a new value as the previous one has been polled from the subject
        assert subject.get_current() == 1  # And the latest value should be updated as well

    @pytest.mark.asyncio
    async def test_get_next_cancelled(self):
        subject = Subject()

        # Will be cancelled, so get_next await call will have to handle cancellation
        async def wait_new_value():
            try:
                await subject.get_next()
            except asyncio.CancelledError:  # Will be cancelled, but we do not want asyncio.gather to throw inside the unit test
                pass

        wait_new_value_task = asyncio.create_task(wait_new_value())

        # Will cancel wait_new_value coroutine
        async def cancel_waiting():
            await asyncio.sleep(0)  # Ensures get_next from wait_new_value is awaited first
            wait_new_value_task.cancel()

        # Wait for get_next then cancel while waiting
        await asyncio.gather(asyncio.create_task(cancel_waiting()), wait_new_value_task)

        # Despite having been cancelled during an await operation, the internal Future object should still work
        subject.next(1)
        assert subject.get_current() == 1

    @pytest.mark.asyncio
    async def test_many_subscribers(self):
        subject = Subject()

        # Awaits a new value and checks it is the expected one in that unit test
        async def wait_new_value():
            print("WAIT")
            assert await subject.get_next() == 1
            print("OK")

        # Many subscribers are waiting for a value
        wait_new_value_tasks = []
        for _ in range(2):
            wait_new_value_tasks.append(asyncio.create_task(wait_new_value()))

        async def push_new_value():
            # Gives hand to the two awaiter tasks before the value is pushed
            for _ in range(2):
                await asyncio.sleep(0)

            print("PUSH")
            subject.next(1)

        await asyncio.gather(asyncio.create_task(push_new_value()), *wait_new_value_tasks)

        # We should be able to push new values on stream
        subject.next(0)
        assert subject.get_current() == 0


class TestServerResponseParsing:
    """Unit tests for different parse_availability_response() test cases."""

    def test_not_enough_args(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("AVAILABILITY 1")  # 2nd arg for players max is missing

    def test_too_many_args(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("AVAILABILITY 1 2 Hello")  # 3rd arg should not be there

    def test_bad_command(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("SOMETHING_UNEXPECTED 1 2")  # Expected 1st word to be the AVAILABILITY command

    def test_invalid_players_count(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("AVAILABILITY Hello 2")  # Expected 1st arg to be an integer

    def test_invalid_players_max(self):
        with pytest.raises(BadResponseSyntax):
            parse_availability_response("AVAILABILITY 1 Hello")  # Expected 2nd arg to be an integer

    def test_everything_fine(self):
        assert parse_availability_response("AVAILABILITY 0 2") == (0, 2)
        assert parse_availability_response("AVAILABILITY 2 3") == (2, 3)


class TestStatusUpdater:
    """Unit tests for StatusUpdater class methods."""

    @pytest.mark.asyncio
    async def test_checkout_server(self, mocker, event_loop, mocked_security_context, mocked_status_subject):
        # Creates a spyable connection instance to mock connction with localhost and check if Python script is behaving as expected
        mocked_websockets_client_protocol = mocker.patch("websockets.WebSocketClientProtocol")
        # Inside a context manager, a WebSocketClientProtocol should be using itself by return self with __aenter__ method
        mocker.patch.object(mocked_websockets_client_protocol, "__aenter__", return_value=mocked_websockets_client_protocol)
        # send() method should be awaitable, this will make it an AsyncMock
        mocker.patch.object(mocked_websockets_client_protocol, "send", unittest.mock.AsyncMock())

        async def mocked_server_response():  # Immediately retrieves a status of 1/2 players connected, but must be awaitable like recv()
            return "AVAILABILITY 1 2"

        # Mocks server response for its status to be 1/2 players connected, it must be passed by a coroutine because the client is
        # awaiting for it
        mocker.patch.object(mocked_websockets_client_protocol, "recv", mocked_server_response)
        # Mocks connection method returning the previously mocked connection instance
        mocked_websockets_connect = mocker.patch("websockets.connect", return_value=mocked_websockets_client_protocol)

        # Now creates a class instance providing only the fields necessary for _checkout_server() method
        updater = StatusUpdater(0, [], mocked_status_subject, mocked_security_context)

        # Performs checkout operation for local port 37373
        checkout_result = await updater._checkout_server(37373)

        # Checks for connection to have been established on secure local port 37373 with the instance SSL context
        # This function is not awaited directly by us so we cannot use assert_awaited* testing functions
        mocked_websockets_connect.assert_called_once_with("wss://localhost:37373", ssl=mocked_security_context)
        # Checks for client to have requested a checkout
        mocked_websockets_client_protocol.send.assert_awaited_once_with("CHECKOUT")

        assert checkout_result == (1, 2)  # Asserts the retrieved server status is 1/2 players, as the server response should have said

    @pytest.mark.asyncio
    async def test_store_retrieved_status_successfully(self, mocker, mocked_status_subject, mocked_security_context):
        # Immediately retrieves a server status with 0/2 players connected, must be awaitable like _checkout_server() method
        async def mocked_successfully_checkout_server(_: int):  # Must take an argument like _checkout_server() method
            return 0, 2

        # Interval ms and ports list are not required for _store_retrieved_status() usage
        updater = StatusUpdater(0, [], mocked_status_subject, mocked_security_context)
        # _checkout_server() is tested somewhere else, here we assume it executes without any error by mocking it
        mocked_checkout_server = mocker.patch.object(updater, "_checkout_server", wraps=mocked_successfully_checkout_server)
        # start() method calling _store_retrieved_status() initializes empty dict before storing result, it is required for method to work
        updater._next_checkout_results = {}

        # Performs a mocked checkout and stores the result inside the instance member
        await updater._store_retrieved_status(37373)  # Checkout on game server local port 37373

        mocked_checkout_server.assert_awaited_once_with(37373)  # Checks for checkout to have been performed on game server at port 37373
        assert updater._next_checkout_results == {37373: (0, 2)}  # A result for this local game server should have been retrieved

    @pytest.mark.asyncio
    async def test_store_retrieved_status_failed(self, mocker, mocked_status_subject, mocked_security_context):
        # Immediately raises an error, must be awaitable like _checkout_server() method
        async def mocked_successfully_checkout_server(_: int):  # Must take an argument like _checkout_server() method
            raise Exception("A random error")

        # Interval ms and ports list are not required for _store_retrieved_status() usage
        updater = StatusUpdater(0, [], mocked_status_subject, mocked_security_context)
        # _checkout_server() is tested somewhere else, here we assume it executes without any error by mocking it
        mocked_checkout_server = mocker.patch.object(updater, "_checkout_server", wraps=mocked_successfully_checkout_server)
        # start() method calling _store_retrieved_status() initializes empty dict before storing result, it is required for method to work
        updater._next_checkout_results = {}

        # Performs a mocked checkout and stores the result inside the instance member
        await updater._store_retrieved_status(37373)  # Checkout on game server local port 37373

        mocked_checkout_server.assert_awaited_once_with(37373)  # Checks for checkout to have been performed on game server at port 37373
        assert updater._next_checkout_results == {37373: None}  # None result means checkout couldn't have been performed on that server

    @pytest.mark.asyncio
    async def test_do_updater_cycle(self, mocker, mocked_status_subject, mocked_security_context):
        current_time_s = 0  # Used to control the currently mocked time in nanoseconds
        server_ports_list = [35555, 35556, 35557, 35558, 35559, 35560]  # List of game server to checkout for
        mocked_checkout_results = {  # Associates a game server port with the result of a checkout operation on that specific game server
            35555: (0, 2),
            35556: (1, 2),
            35557: None,
            35558: (2, 2),
            35559: (0, 2),
            35560: None,
        }

        checkout_delay = asyncio.Event()  # Will be set to indicates checkout operations on game server have completed successfully

        def mocked_time() -> int:  # Will returns current_time_s, mocked to decide which time a series of checkout operations is taking
            return current_time_s

        # Copies mocked result inside instance stored result, sometimes checkout times out to verify these errors are handled properly
        async def mocked_store_retrieved_status(port: int):
            if port == 35557 or port == 35560:  # For these 2 ports, emulates a game server which is not responding
                # This will cause checkout operation to not complete in time, when timed out, a task is cancelled so we're not assigning
                # None to the corresponding server status entry
                raise asyncio.TimeoutError()

            # By waiting this event, we allow the unit test to change current_time_s before measuring checkout operation duration
            await checkout_delay.wait()
            updater._next_checkout_results[port] = mocked_checkout_results[port]

        # Interval and ports list are used by _do_updater_cycle() method so they're provided here with a mocked Subject to check if new
        # checkout results are published as expected
        updater = StatusUpdater(5000, server_ports_list, mocked_status_subject, mocked_security_context)

        mocker.patch("time.time", mocked_time)  # Provides a time piloted by this unit test
        mocker.patch.object(updater, "_store_retrieved_status", mocked_store_retrieved_status)  # Provides checkout results piloted by test
        mocked_sleep = mocker.patch("asyncio.sleep")  # Spies duration with which this function is called
        mocker.patch("rptminigameshub.checkout.logger.error")  # Spies if error of timed out checkout was logged as expected

        async def fast_forward_time_then_continue():
            await asyncio.sleep(0)  # Ensures checkout series has begun before we modifies the time

            nonlocal current_time_s
            current_time_s = 2.5  # We end cycle at time 2500 ms, it took 1500 ms

            checkout_delay.set()

        current_time_s = 1  # We begin checkout series (updater cycle) at time 1000 ms
        await asyncio.gather(  # Starts updater cycle, then fast forward time during 1500 mocked ms
            asyncio.create_task(updater._do_updater_cycle()),
            asyncio.create_task(fast_forward_time_then_continue())
        )

        # We expect new status list retrieved from mock to have been pushed inside hub subject, so it can be used by the network module
        mocked_status_subject.next.assert_called_once_with(mocked_checkout_results)

        # As some checkout operations timed out, an error should have been logged to signal this
        rptminigameshub.checkout.logger.error.assert_called_once()

        # As initial interval duration between 2 cycles is 5000 ms and this cycle ran for 1500 ms, it should sleep 3500 ms until the next
        # cycle can run
        mocked_sleep.assert_called_with(3.5)  # sleep() takes a duration in seconds

        # This final checkout results dict should correspond to the status retrieved by checkout operations, here it is the same as the
        # mocked results dict
        assert updater._next_checkout_results == mocked_checkout_results

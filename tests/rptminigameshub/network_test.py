import unittest.mock

from rptminigameshub.network import *
import pytest
import asyncio
import websockets


class TestClientsListener:
    """Unit tests for ClientsListener class methods."""

    @pytest.fixture
    def mocked_client_connection(self, mocker, request):
        """Provides a mocked client connection with `WebSocketServerProtocol`, the recv() method returns the value inside request's
        param."""

        async def mocked_recv():
            return request.param

        mocked_connection = mocker.patch("websockets.WebSocketServerProtocol")  # Creates a mockable connection object
        mocker.patch.object(mocked_connection, "recv", mocked_recv)  # Mocks a client which is sending the user-requested message

        return mocked_connection

    @pytest.fixture
    async def error_task(self):
        """Provides an asyncio task which is immediately raising an error."""

        async def task():
            raise RuntimeError("A random error")

        return asyncio.create_task(task())

    @pytest.fixture
    async def infinite_task(self):
        """Provides an asyncio task which is awaiting indefinitely and which can only be stopped using cancellation."""

        async def task():
            await asyncio.Event().wait()  # Will wait indefinitely

        return asyncio.create_task(task())

    # Because some unit test might require two concurrent tasks running indefinitely
    second_infinite_task = infinite_task

    @pytest.fixture
    async def mocked_client_endpoint(self):
        """Provides an emulated client endpoint passed to every task and method."""

        return "127.0.0.1:50505"

    @pytest.fixture
    async def server_with_mocked_conditions(self, mocker, mocked_status_subject, mocked_security_context, mocked_client_endpoint, request):
        """Provides a ClientListener instance with mocked conditions awaiting coroutine to check for subroutines provided arguments."""

        # Mocked listener instance to invoke tested method. For that method neither port, games data, SSL features nor status subject
        # are important
        server = ClientsListener(0, [], mocked_security_context, mocked_status_subject)

        # Performs argument checking to control if arguments used with condition waiting coroutines are correct
        # Will return desired value to control case where connection is closed or not, or immediately raises error if None is passed
        async def mocked_condition_waiting(require_update, client_request_condition, new_status_condition, client_endpoint):
            if request.param is None:  # To tests the case where an exception is raided by this subroutine
                raise RuntimeError()

            # Performs arguments checking instead of starting conditions awaiting coroutines
            assert client_endpoint == mocked_client_endpoint
            assert not require_update.is_set()

            return request.param

        mocker.patch("rptminigameshub.network.ClientsListener._wait_for_required_update", mocked_condition_waiting)

        return server

    # Uses a mocked connection from a client sending "A BAD REQUEST"
    @pytest.mark.parametrize("mocked_client_connection", ["A BAD REQUEST"], indirect=True)
    @pytest.mark.asyncio
    async def test_wait_for_client_request_with_bad_request(self, mocker, event_loop, mocked_client_connection):
        condition_fulfilled_event = asyncio.Event()  # Event passed to method, is set at the end of it

        with pytest.raises(BadClientRequest):  # We mocked client to send a bad request, so an error will be raised
            # Client endpoint for logging purpose doesn't matter here
            await ClientsListener._wait_for_client_request(mocked_client_connection, condition_fulfilled_event, "")

        # Error should have been raised before setting event as client hasn't requested the update properly
        assert not condition_fulfilled_event.is_set()

    # Uses a mocked connection from a client sending "REQUEST"
    @pytest.mark.parametrize("mocked_client_connection", ["REQUEST"], indirect=True)
    @pytest.mark.asyncio
    async def test_wait_for_client_request_with_good_request(self, mocker, event_loop, mocked_client_connection):
        condition_fulfilled_event = asyncio.Event()  # Event passed to method, is set at the end of it

        # Client endpoint for logging purpose doesn't matter here
        await ClientsListener._wait_for_client_request(mocked_client_connection, condition_fulfilled_event, "")

        # Coroutine method should have completed successfully, so the event is set
        assert condition_fulfilled_event.is_set()

    def test_update_servers_data(self, mocked_status_subject, mocked_security_context):
        initial_servers_data = [  # Game servers data given to ctor without the "availability" properties
            {"name": "Açores", "game": "A", "port": 35555},
            {"name": "Bermudes", "game": "B", "port": 35557},
            {"name": "Canaries", "game": "C", "port": 35559}
        ]

        # Port number isn't used by this method, but game servers data is used to assigns the "availability" property on each listed
        # game server
        server = ClientsListener(0, initial_servers_data, mocked_security_context, mocked_status_subject)

        server._update_servers_data({
            35555: (0, 2),
            35557: None,
            35559: (2, 2)
        })
        # Checks for the updated game servers data to be the same as initialized but with "availability" properties assigned
        assert server._current_servers_data == [
            {
                "name": "Açores", "game": "A", "port": 35555, "availability": {
                    "playersCount": 0, "playersLimit": 2
                }
            },
            {
                "name": "Bermudes", "game": "B", "port": 35557, "availability": None
            },
            {
                "name": "Canaries", "game": "C", "port": 35559, "availability": {
                    "playersCount": 2, "playersLimit": 2
                }
            }
        ]

        server._update_servers_data({
            35555: (1, 2),
            35557: (0, 2),
            35559: None
        })
        # Same check as before, excepted than this time we're checking for properties to be updated even if they're already assigned
        assert server._current_servers_data == [
            {
                "name": "Açores", "game": "A", "port": 35555, "availability": {
                    "playersCount": 1, "playersLimit": 2
                }
            },
            {
                "name": "Bermudes", "game": "B", "port": 35557, "availability": {
                    "playersCount": 0, "playersLimit": 2
                }
            },
            {
                "name": "Canaries", "game": "C", "port": 35559, "availability": {
                    "playersCount": 2, "playersLimit": 2  # Checkout failed (None value) so we keep the last status assigned
                }
            }
        ]

    @pytest.mark.asyncio
    async def test_wait_for_new_status(self, mocker, mocked_status_subject, mocked_security_context):
        async def mocked_get_next():  # Mocks a servers list containing one server on port 35555 having already 1 player connected
            return {35555: (1, 2)}

        # Unit test pilotes which servers are listed and what is their status
        mocker.patch.object(mocked_status_subject, "get_next", mocked_get_next)
        # We mocks a game server checkout on 35555, this server data must be passed to ClientsListener ctor to exist inside instance
        # servers data so it can be updater later
        initial_servers_data = [{"name": "Açores", "game": "A", "port": 35555}]

        # Port number isn't used here. Mocked subject allows us to provide arbitral servers checkout results
        server = ClientsListener(0, initial_servers_data, mocked_security_context, mocked_status_subject)
        # We don't care about instance data here, we just check if it is updated with correct retrieved status
        mocked_update_servers_data = mocker.patch.object(server, "_update_servers_data")

        condition_fulfilled = asyncio.Event()  # Set at end of the tested method

        await server._wait_for_new_status(condition_fulfilled, "")  # Client endpoint for logging purpose doesn't matter here

        assert condition_fulfilled.is_set()  # Should have been set as method should have reached its end without errors
        mocked_update_servers_data.assert_called_once_with({35555: (1, 2)})  # Checks if instance data is updated with published data

    @pytest.mark.asyncio
    async def test_wait_for_required_update_unexpected_error(self, error_task, infinite_task):
        with pytest.raises(RuntimeError):  # error_task raises an error which is unexpected, so it is transmitted through the caller
            # Event is not modified by this static method itself so its behavior and value isn't interesting for us
            await ClientsListener._wait_for_required_update(asyncio.Event(), error_task, infinite_task, "")

        # Performs a whole event loop cycle to ensures condition tasks cancellation requests have been handled by asyncio
        await asyncio.sleep(0)

        # Method should ensure both given condition task are finished to prepare the next client handling cycle, even if an error was
        # raised
        assert error_task.done()
        assert infinite_task.done()

    @pytest.mark.asyncio
    async def test_wait_for_required_update_condition_task_cancelled(self, infinite_task, second_infinite_task):
        async def cancel_one_condition_task():  # Cancels one of the two tasks waiting for updating required condition
            second_infinite_task.cancel()

        # As cancellation is not caused by connection closure or by the other task being finished, the error must be propagated
        with pytest.raises(asyncio.CancelledError):
            tested_method_task = asyncio.create_task(
                ClientsListener._wait_for_required_update(asyncio.Event(), infinite_task, second_infinite_task, "")
            )

            # Waits for both tasks then unexpectedly cancels one of them
            await asyncio.gather(tested_method_task, asyncio.create_task(cancel_one_condition_task()))

        # Method should ensure both given condition task are finished to prepare the next client handling cycle, even if an error was
        # raised
        assert infinite_task.done()
        assert second_infinite_task.done()

    @pytest.mark.asyncio
    async def test_wait_for_required_update_connection_closed(self, infinite_task):
        async def stop_recv_connection_closed():  # Emulates a recv() awaiting coroutine interrupted because of a closed connection
            # Connection closed normally in that case, but it could also be closed with another code than 1000
            raise websockets.ConnectionClosedOK(1000, "")

        # Must be accessible to check if it was properly cancelled by method
        mocked_client_listener_task = asyncio.create_task(stop_recv_connection_closed())

        # As connection will be closed, it will execute normally with a return value of True
        connection_closed = await ClientsListener._wait_for_required_update(
            asyncio.Event(), mocked_client_listener_task, infinite_task, ""
        )

        # Performs a whole event loop cycle to ensures condition tasks cancellation requests have been handled by asyncio
        await asyncio.sleep(0)

        assert connection_closed  # ConnectionClosed should have been caught
        # Both condition awaiting tasks should be finished at method exit
        assert mocked_client_listener_task.done()
        assert infinite_task.done()

    @pytest.mark.asyncio
    async def test_wait_for_required_update_one_condition_task_finished(self, infinite_task):
        require_update = asyncio.Event()  # Event passed to condition awaiting coroutines, fired when a condition is fulfilled

        async def mocked_condition_task():  # Immediately fire the require_update event
            require_update.set()

        mocked_new_status_list_awaiter = asyncio.create_task(mocked_condition_task())

        # As one condition task finished, it should have fired the require_update event, so we expect function to normally return with
        # the value False
        connection_closed = await ClientsListener._wait_for_required_update(
            require_update, infinite_task, mocked_new_status_list_awaiter, ""
        )

        assert not connection_closed  # No ConnectionClosedError caught
        # Both condition awaiting tasks should be finished at method exit
        assert infinite_task.done()
        assert mocked_new_status_list_awaiter.done()

    @pytest.mark.parametrize("server_with_mocked_conditions", [True], indirect=True)
    @pytest.mark.asyncio
    async def test_client_serving_cycle_connection_closed(self, mocker, server_with_mocked_conditions, mocked_client_endpoint):
        # Mocks connection to check for operations done on it
        mocked_client_connection = mocker.patch("websockets.WebSocketServerProtocol")
        # send() must be awaitable, so we manually assign an async mocked method to it
        mocked_send = mocker.patch.object(mocked_client_connection, "send", unittest.mock.AsyncMock())

        continue_serving_client = await server_with_mocked_conditions._client_serving_cycle(
            mocked_client_connection, mocked_client_endpoint
        )

        # As connection has been closed, we should no longer be serving this client
        mocked_send.assert_not_called()
        assert not continue_serving_client

    @pytest.mark.parametrize("server_with_mocked_conditions", [False], indirect=True)
    @pytest.mark.asyncio
    async def test_client_serving_cycle_connection_still_open(self, mocker, server_with_mocked_conditions, mocked_client_endpoint):
        # Mocks connection to check for operations done on it
        mocked_client_connection = mocker.patch("websockets.WebSocketServerProtocol")
        # send() must be awaitable, so we manually assign an async mocked method to it
        mocked_send = mocker.patch.object(mocked_client_connection, "send", unittest.mock.AsyncMock())

        continue_serving_client = await server_with_mocked_conditions._client_serving_cycle(
            mocked_client_connection, mocked_client_endpoint
        )

        # As connection is still open, we should continue to serve this client
        mocked_send.assert_called_once()
        assert continue_serving_client

    @pytest.mark.parametrize("server_with_mocked_conditions", [None], indirect=True)
    @pytest.mark.asyncio
    async def test_client_serving_cycle_connection_error_raised(self, mocker, server_with_mocked_conditions, mocked_client_endpoint):
        # Mocks connection to check for operations done on it
        mocked_client_connection = mocker.patch("websockets.WebSocketServerProtocol")
        # send() must be awaitable, so we manually assign an async mocked method to it
        mocked_send = mocker.patch.object(mocked_client_connection, "send", unittest.mock.AsyncMock())

        # Internal tasks awaiting throws error as None parameter has been given to mocked ClientsListener fixture
        with pytest.raises(RuntimeError):
            continue_serving_client = await server_with_mocked_conditions._client_serving_cycle(
                mocked_client_connection, mocked_client_endpoint
            )

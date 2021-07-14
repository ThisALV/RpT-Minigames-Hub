from rptminigameshub.network import *
import pytest


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
            {"name": "Açores", "game": "A", "port": 35555, "availability": (0, 2)},
            {"name": "Bermudes", "game": "B", "port": 35557, "availability": None},
            {"name": "Canaries", "game": "C", "port": 35559, "availability": (2, 2)}
        ]

        server._update_servers_data({
            35555: (1, 2),
            35557: (0, 2),
            35559: None
        })
        # Same check as before, excepted than this time we're checking for properties to be updated even if they're already assigned
        assert server._current_servers_data == [
            {"name": "Açores", "game": "A", "port": 35555, "availability": (1, 2)},
            {"name": "Bermudes", "game": "B", "port": 35557, "availability": (0, 2)},
            {"name": "Canaries", "game": "C", "port": 35559, "availability": None}
        ]

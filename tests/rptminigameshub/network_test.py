import asyncio

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

import asyncio
import ssl
import logging
import rptminigameshub.checkout
import websockets
import json
import traceback


# Initializes and retrieves this module logger
logger = logging.getLogger(__name__)


class BadClientRequest(RuntimeError):
    """Internally thrown and caught by `ClientsListener` if it sent a message which isn't `REQUEST`. Should not by manipulated by module
    user."""

    def __init__(self):
        super().__init__()


class ClientsListener:
    """Listens for incoming WSS connections on given port, then waits for clients to send a `REQUEST` message or for source Subject to emit
    a value for sending the new game servers data to clients."""

    def __init__(self, port: int, servers_config: "list[dict]", security_ctx: ssl.SSLContext, status_source: rptminigameshub.checkout.Subject):
        """Configures shortly started server to listen on given port with given security context configuration. New status are obtained
        from given source Subject.
        Servers configuration argument contains details about each server which are not related to their status or availability. These
        details will be sent to client with retrieved status data."""

        self.port = port
        self.security_ctx = security_ctx
        self.status_source = status_source

        # Servers data will be sent as JSON to the clients, so we save the given list as it and we'll change the "availability"
        # value when new status will be retrieved from local game servers.
        self._current_servers_data = servers_config
        # A None value for status means it is currently unknown, so we initialize each game server data with an unknown current status
        for game_server_data in self._current_servers_data:
            game_server_data["availability"] = None

    def _update_servers_data(self, current_checkout_results: "dict[int, tuple[int, int]]"):
        """With given game server status dict, update "availability" fields into instance game servers data so we can later convert
        this data into JSON to sent it to a client."""

        for game_server_data in self._current_servers_data:  # Each game server needs to have its data updated
            # Retrieves checkout operation result using current game server port
            server_checkout_result = current_checkout_results[game_server_data["port"]]

            # If the checkout operation failed, we have no status to assigns inside this server data se we keep the last status obtained
            if server_checkout_result is not None:
                game_server_data["availability"] = {  # Updates status data inside this game server data
                    "playersCount": server_checkout_result[0],  # 1st tuple element is number of players currently connected
                    "playersLimit": server_checkout_result[1]  # 2nd tuple element is the maximum number of players accepted at the same time
                }

    @staticmethod
    async def _wait_for_client_request(connection: websockets.WebSocketServerProtocol, require_update: asyncio.Event, client_endpoint: str):
        """Waits for a REQUEST message to be received on given connection then fires given event."""

        message = await connection.recv()  # Waits for a message to be received from client, will throw if connection is closed

        if message != "REQUEST":  # Checks if client request for servers data update is valid
            logger.error(f"Client {client_endpoint} sent a bad request: \"{message}\"")
            raise BadClientRequest()

        logger.debug(f"Update request sent by {client_endpoint}.")
        require_update.set()

    async def _wait_for_new_status(self, require_update: asyncio.Event, client_endpoint: str):
        """Waits for a new value to be published inside status list subject then updates servers data and fires given event."""

        new_status_list = await self.status_source.get_next()  # Waits for an eventually updated list of servers status
        self._update_servers_data(new_status_list)  # Updates current game servers data with new "availability" properties

        logger.debug(f"New list inside data source, will be updated for {client_endpoint}.")
        require_update.set()

    @staticmethod
    async def _wait_for_required_update(require_update: asyncio.Event, client_request_condition: asyncio.Task, new_status_condition: asyncio.Task, client_endpoint: str) -> bool:
        """Waits for 1 of the 2 given tasks to finish or to be cancelled, then cancel the other one. This method ensures the two given 
        tasks are cancelled when it returns.
        Returns true if a `ConnectionClosed` was raised during the tasks awaiting, `false` otherwise."""

        connection_closed = False  # Will be set to True when a connection closed error will be caught

        async def wait_for_one_condition():  # Waits for one of the two required condition to update to be met and prepares next cycle
            await require_update.wait()
            prepare_next_cycle()  # Cancellation required to stop being awaiting for asyncio.gather() call

        def prepare_next_cycle():  # Prepares the next loop cycle by cleaning every possibly running task for current cycle
            client_request_condition.cancel()
            new_status_condition.cancel()

        condition_awaiting_task = asyncio.create_task(wait_for_one_condition())

        try:
            logger.debug(f"Waiting for update to be required for client {client_endpoint}...")
            # Runs task to wait for one of the two condition, then performs tasks cleaning work when one condition if fulfilled
            await asyncio.gather(client_request_condition, new_status_condition, condition_awaiting_task)
        except websockets.ConnectionClosed:  # If client_request_condition thrown and connection with client is closed
            connection_closed = True  # We must no longer be sending game servers data on this condition
        except asyncio.CancelledError:
            # If connection has been closed or a new game servers sync must be done with the client, then it normal that condition
            # tasks for this cycle are cancelled to prepare the new cycle
            if not (connection_closed or require_update.is_set()):
                raise  # If it not the case, then this error is abnormal and must be transmitted
        finally:  # If error raised, avoids tasks to running silently in background. If not, prepares the next cycle tasks.
            prepare_next_cycle()  # Might be necessary in case of an error raised at any moment

        return connection_closed

    async def _client_serving_cycle(self, connection: websockets.WebSocketServerProtocol, client_endpoint: str) -> bool:
        """Performs a serving cycle for the client, that is, waits for a request to be received or for a new value to be published, then
        sends new game servers data to this client.
        Unexpected errors are caught by caller.
        Returns `true` if connection is still open, `false` otherwise."""
        
        require_update = asyncio.Event()  # This event will be set when one of the two conditions for game servers data to be sent is met

        # The two possible conditions for game servers data to be sent again into client connection
        client_request_condition = asyncio.create_task(ClientsListener._wait_for_client_request(connection, require_update, client_endpoint))
        new_status_list_condition = asyncio.create_task(self._wait_for_new_status(require_update, client_endpoint))

        # Will wait until a condition required to send updated servers data is met, also returning if connection was closed when listening
        # for a client request inside client_request_condition task
        connection_closed = await ClientsListener._wait_for_required_update(
            require_update, client_request_condition, new_status_list_condition, client_endpoint
        )

        if not connection_closed:  # Doesn't try to send data if connection was closed when we were awaiting
            logger.debug(f"Sending new servers data for {client_endpoint}...")
            # Supports UTF-8 and disables pretty-printing for sent JSON data
            await connection.send(json.dumps(self._current_servers_data, indent=None, ensure_ascii=False))
            logger.debug(f"Sent data for {client_endpoint}.")

        return not connection_closed

    async def _handle_client(self, connection: websockets.WebSocketServerProtocol):
        """Waits for a REQUEST message to be received on given connection or for a new list of game servers data to be published and
        then send in JSON this new data into the given connection, and repeat until connection is closed."""

        client_endpoint_str = format("%d:%d", *connection.remote_address)  # Connection remote endpoint is a tuple of (host, port)
        logger.info(f"Serving client {client_endpoint_str}...")

        try:  # An error which is occurring for a client might not be propagated, it should only crash the serving process for that client
            # Will stops if serving cycle returns False, that is, if connection with client is closed
            while self._client_serving_cycle(connection, client_endpoint_str):
                pass
        except Exception as err:
            err_msg = err.args[0] if len(err.args) > 0 else ""

            logger.error(f"Client {client_endpoint_str}: {type(err).__name__}: {err_msg}")
            logger.error(traceback.format_exc())

        logger.info(f"Disconnected client {client_endpoint_str}.")

    async def start(self):
        """Starts a WSS server with instance configuration. Will automatically closes WSS server when exited."""

        logger.debug(f"Opening server on port {self.port}...")
        # Opens a WSS server on configured port with selected certificate and private key, then automatically closes it when exited
        async with websockets.serve(self._handle_client, host=None, port=self.port, ssl=self.security_ctx) as server:
            logger.info(f"Server open. Listening for WSS clients on port {self.port}...")
            await asyncio.Event().wait()  # Will waits indefinitely until the task is cancelled from main script with a Ctrl+C

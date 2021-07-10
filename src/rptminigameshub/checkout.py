import asyncio
import logging
import ssl
import websockets
import time


# Initializes and retrieves this module logger
logger = logging.getLogger(__name__)


class BadResponseSyntax(RuntimeError):
    """Thrown by `parse_availability_response()` if command or arguments are incorrect."""

    def __init__(self, reason: str, actual_command: str):
        """Constructs a `RuntimeError` with a formatted error message containing violated syntax rule and command which
        led to that error."""

        super(f"Rule: {reason}, Actual command: {actual_command}")


def parse_availability_response(availability_response: str) -> "tuple[int, int]":
    """With given server AVAILABILITY command RPTL message, parses server status, throwing `BadResponseSyntax` if server responded badly."""

    # Split by words check if response syntax is correct
    words = availability_response.split(" ")

    if len(words) < 3:  # If there isn't one word for command and two args, then command words cannot be parsed as expected
        raise BadResponseSyntax("Syntax is AVAILABILITY <players_number> <maximum>", availability_response)

    try:  # We might fail to parse arguments if players count data are not integers, in that case it is a syntax error
        command_name = words[0]
        players_count = int(words[1])
        players_maximum = int(words[2])
    except ValueError:
        raise BadResponseSyntax("players_number and maximum args must be valid integers", availability_response)

    if command_name != "AVAILABILITY":  # We must check if server responses corresponds to our checkout request
        raise BadResponseSyntax("CHECKOUT server response must be an AVAILABILITY command", availability_response)

    return players_count, players_maximum


class Subject:
    """Subscribable subject to await for next value emitted by it. Can be used inside coroutine functions to wait for another operation to produce a new data
    inside this subject."""

    def __init__(self):
        """Initializes subject with no subscriber and no values already pushed."""
        pass

    def next(self, value):
        """Provides each subscriber with data given as argument."""
        pass


class StatusUpdater:
    """Periodically performs a checkout on every listed server to update a subject containing latest known servers status."""

    def __init__(self, interval_ms: int, servers_list: "list[int]", status_target: Subject, local_security_context: ssl.SSLContext):
        """Configures shortly started periodic updater to perform checkouts every given interval in milliseconds with localhost:<port>
        where <port> is each integer inside servers_list and to publish operation result on given target Subject.
        Given security context is used to accept game server TLS certificate even if it is not signed for `localhost` hostname."""

        self.interval_ms = interval_ms
        self.servers_list = servers_list
        self.status_target = status_target
        self.security_context = local_security_context

        # The next checkout series results that will be published inside subject, has to be accessed from multiple class coroutines
        self.next_checkout_results = None

    async def store_retrieved_status(self, server_port: int):  # Performs a checkout operation for a single server then stores result
        try:
            self.next_checkout_results[server_port] = await self.checkout_server(server_port)
        except Exception as err:  # An error occurring at a single server checkout must NOT crash the entire hub system
            # Optional error message, might be empty if no additional data given to exception
            err_msg = err.args[0] if len(err.args) > 0 else ""
            # Instead, we log the current error...
            logger.error(f"Server {server_port}: {type(err).__name__}: {err_msg}")

            # ...and we signal status hasn't be retrieving successfully with a None value
            self.next_checkout_results[server_port] = None

    async def start(self):
        """Starts periodic updates with instance configuration. Dictionary containing results for every server status is published inside
        selected Subject when ALL checkouts are done."""

        while True:  # Repeats that asynchronous task indefinitely, will be exited when running task will be stopped by Ctrl+C
            operation_begin_ms = time.time_ns() * 10 ** -6  # Keeps track of when the operation began to mesure its duration
            self.next_checkout_results = {}  # Resets the results dictionary of the previous operation results

            checkout_tasks = []
            for port in self.servers_list:  # Run checkout operation concurrently because we're doing the same task on 6 different connections
                checkout_tasks.append(asyncio.create_task(self.store_retrieved_status(port)))

            try:  # Avoids a situation where a new checkout series begin before the previous one is currently running with wait_for
                await asyncio.wait_for(asyncio.gather(checkout_tasks), self.interval_ms)
            except asyncio.TimeoutError:
                logger.error("Some game server checkouts didn't complete before delay end, they're cancelled.")

            # Calculates the final duration of this checkout series operation
            operation_end_ms = time.time_ns() * 10 ** -6  # Conversion from ns to ms -> 10^-6 units
            operation_duration_ms = operation_end_ms - operation_begin_ms

            # Waits the remaining time of the interval, aka the total interval time - time passed to perform the current checkout series
            await asyncio.sleep(self.interval_ms - operation_duration_ms)

    async def checkout_server(self, server_port: int) -> "tuple[int, int]":
        """Asynchronously connect to a locally hosted game server and sends CHECKOUT command, then await for response and returns a tuple containing:
        1st the current number of players connected, 2nd the maximal number of players accepted."""

        # Tries to connect using secure WebSocket with local game server
        async with websockets.connect(f"wss://localhost:{server_port}", ssl=self.security_context) as connection:
            await connection.send("CHECKOUT")  # When connected, sends a checkout command to game server
            server_response = await connection.recv()  # When request sent, wait for the serve response to be received

            return parse_availability_response(server_response)  # Tries to parse its response and retrieves the result tuple

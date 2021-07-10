import logging
import ssl


# Initializes and retrieves this module logger
logger = logging.getLogger(__name__)


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
        pass

    async def start(self):
        """Stats periodic updates with instance configuration. Dictionary containing results for every server status is published inside
        selected Subject when ALL checkouts are done.

        Checkouts are *NOT* performed concurrently."""
        pass

    async def checkout_server(self, server_port: int) -> "tuple[int, int]":
        """Asynchronously connect to a locally hosted game server and sends CHECKOUT command, then await for response and returns a tuple containing:
        1st the current number of players connected, 2nd the maximal number of players accepted."""
        pass

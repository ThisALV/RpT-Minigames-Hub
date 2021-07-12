import ssl
import logging
import rptminigameshub.checkout


# Initializes and retrieves this module logger
logger = logging.getLogger(__name__)


class ClientsListener:
    """Listens for incoming WSS connections on given port, then waits for clients to send a `REQUEST` message or for source Subject to emit
    a value for sending the new game servers data to clients."""

    def __init__(self, port: int, servers_config: "dict", security_ctx: ssl.SSLContext, status_source: rptminigameshub.checkout.Subject):
        """Configures shortly started server to listen on given port with given security context configuration. New status are obtained
        from given source Subject.
        Servers configuration argument contains details about each server which are not related to their status or availability. These
        details will be sent to client with retrieved status data."""
        pass

    async def start(self):
        """Starts a WSS server with instance configuration. Will automatically closes WSS server when exited."""
        pass

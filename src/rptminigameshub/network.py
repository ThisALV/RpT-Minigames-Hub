import ssl
import logging
import rptminigameshub.checkout


# Initializes and retrieves this module logger
logger = logging.getLogger(__name__)


class ClientsListener:
    """Listens for incoming WSS connections on given port, then uses established connections with StatusEmitter."""

    def __init__(self, port: int, security_ctx: ssl.SSLContext, status_source: rptminigameshub.checkout.Subject):
        """Configures shortly started server to listen on given port with given security context configuration. New status are obtained
        from given source Subject."""
        pass

    async def __aenter__(self):
        """Starts a WSS server with instance configuration. Current asyncio event's loop must be run after this call to handle new connections."""
        pass

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stops currently open WSS server."""
        pass

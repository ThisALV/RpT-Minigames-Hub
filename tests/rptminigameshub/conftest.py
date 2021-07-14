import pytest


@pytest.fixture
def mocked_security_context(mocker):
    """Provides a mocked `ssl.SSLContext` object to use with `StatusUpdater` ctor."""

    return mocker.patch("ssl.SSLContext")


@pytest.fixture
def mocked_status_subject(mocker):
    """Provides a mocked `Subject` object to use with `StatusUpdater` ctor."""

    return mocker.patch("rptminigameshub.checkout.Subject")

import pytest

from acceptance.runner import Driver


@pytest.fixture
def driver() -> Driver:
    """Connect this fixture to the app when `pagehost.bootstrap.create_server` exists.

    Until then, scenario tests stay skipped. The semantic matcher and the
    operation runner are covered without a server.
    """
    pytest.skip("pagehost app is not connected to the acceptance driver yet")

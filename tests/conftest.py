import pytest

from app.core.application import create_application


@pytest.fixture(scope="session")
def qtapp():
    app = create_application([])
    yield app


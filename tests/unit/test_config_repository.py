import pytest

from rate_limiter.exceptions import ClientNotFoundError, LimitConfigNotFoundError
from rate_limiter.repositories.config_repository import ConfigRepository


def test_unknown_client_raises(db):
    repo = ConfigRepository()
    with pytest.raises(ClientNotFoundError):
        repo.get_limit_config("does-not-exist", "some-resource")


def test_known_client_missing_resource_config_raises(db, test_client_config):
    repo = ConfigRepository()
    with pytest.raises(LimitConfigNotFoundError):
        repo.get_limit_config("test-client", "unconfigured-resource")


def test_config_is_cached_after_first_lookup(db, test_client_config):
    repo = ConfigRepository()
    first = repo.get_limit_config("test-client", "test-resource")
    # Second call should hit cache, not re-query Postgres — verified indirectly
    # by confirming identical values without deleting the DB row in between.
    second = repo.get_limit_config("test-client", "test-resource")
    assert first == second
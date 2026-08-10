import pytest
from fastapi import HTTPException

from aihr.services.operations_auth import require_operations_access


def test_operations_access_requires_matching_bearer_token() -> None:
    require_operations_access(
        configured_token="secret",
        authorization="Bearer secret",
        environment="online",
    )

    with pytest.raises(HTTPException) as exc:
        require_operations_access(
            configured_token="secret",
            authorization="Bearer wrong",
            environment="online",
        )
    assert exc.value.status_code == 401


def test_online_environment_rejects_missing_operations_configuration() -> None:
    with pytest.raises(HTTPException) as exc:
        require_operations_access(
            configured_token="",
            authorization=None,
            environment="online",
        )
    assert exc.value.status_code == 503

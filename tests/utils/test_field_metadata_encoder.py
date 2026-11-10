import json

import pytest
from pydantic import Field

from mcp_agent.utils.pydantic_type_serializer import PydanticTypeEncoder


@pytest.mark.parametrize("constrained", [False, True])
def test_field_info_json_encoding(constrained: bool) -> None:
    field = Field(default=2, description="count", **({"gt": 0} if constrained else {}))
    result = json.loads(json.dumps(field, cls=PydanticTypeEncoder))
    assert result["__pydantic_field_info__"] is True
    assert result["default"] == 2
    assert result["description"] == "count"
    assert len(result["metadata"]) == (1 if constrained else 0)

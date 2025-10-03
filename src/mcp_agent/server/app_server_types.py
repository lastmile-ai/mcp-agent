from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, create_model
# from pydantic.json_schema import model_from_schema

from mcp.types import (
    CreateMessageResult,
    SamplingMessage,
)

MCPMessageParam = SamplingMessage
MCPMessageResult = CreateMessageResult


def create_model_from_schema(json_schema: Dict[str, Any]) -> Type[BaseModel]:
    """Create a Pydantic model from a JSON schema"""
    model_name = json_schema.get("title", "DynamicModel")
    properties = json_schema.get("properties", {})
    required = json_schema.get("required", [])

    field_definitions = {}

    for field_name, field_schema in properties.items():
        # Get field type
        field_type = str  # Default to string
        schema_type = field_schema.get("type")

        if schema_type == "integer":
            field_type = int
        elif schema_type == "number":
            field_type = float
        elif schema_type == "boolean":
            field_type = bool
        elif schema_type == "array":
            field_type = List[Any]
        elif schema_type == "object":
            field_type = Dict[str, Any]

        # Handle optional fields
        if field_name not in required:
            field_type = Optional[field_type]

        # Create field with basic info
        field_info = {}
        if "description" in field_schema:
            field_info["description"] = field_schema["description"]

        field_definitions[field_name] = (field_type, Field(**field_info))

    return create_model(model_name, **field_definitions)

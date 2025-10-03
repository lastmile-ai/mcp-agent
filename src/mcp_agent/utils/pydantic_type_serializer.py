"""
Serializer for Pydantic model types.
This allows model types to be transmitted between different processes or services,
such as in a distributed workflow system like Temporal.
"""

import json
import inspect
import importlib
from enum import Enum
from datetime import datetime, date, time
import re
import enum
import uuid
import logging
from typing import (
    Any,
    Dict,
    List,
    Set,
    Tuple,
    Union,
    Optional,
    Type,
    TypeVar,
    get_origin,
    get_args,
    ForwardRef,
    Annotated,
    Literal,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    PrivateAttr,
    ValidationInfo,
    model_validator,
    create_model,
    ConfigDict,
)
from pydantic.fields import FieldInfo
from pydantic._internal._utils import lenient_issubclass

# Set up logging
logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def is_pydantic_undefined(obj: Any) -> bool:
    """Check if an object is a PydanticUndefinedType instance."""
    if obj is None:
        return False
    return (
        hasattr(obj, "__class__") and obj.__class__.__name__ == "PydanticUndefinedType"
    )


def make_serializable(value: Any) -> Any:
    """Make a value serializable by handling PydanticUndefinedType and other special cases."""
    if is_pydantic_undefined(value):
        return None
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if value is ...:
        return None
    try:
        json.dumps(value)  # Test if already serializable
        return value
    except (TypeError, OverflowError):
        return str(value)


class PydanticTypeSerializer(BaseModel):
    """
    A utility class for serializing and reconstructing Pydantic model types.
    This allows model types to be transmitted between different processes or services,
    such as in a distributed workflow system.
    """

    class Config:
        arbitrary_types_allowed = True

    @staticmethod
    def _get_type_origin_name(origin: Any) -> str:
        """Get a standardized name for a type origin."""
        if origin is Union:
            return "Union"
        elif origin is list:
            return "List"
        elif origin is dict:
            return "Dict"
        elif origin is set:
            return "Set"
        elif origin is tuple:
            return "Tuple"
        elif origin is Literal:
            return "Literal"
        elif origin is type:
            return "Type"
        elif origin is Annotated:
            return "Annotated"
        elif origin is None:
            return "None"
        else:
            # For less common types, use the best name we can find
            return getattr(origin, "__name__", str(origin))

    @staticmethod
    def serialize_type(typ: Any) -> Dict[str, Any]:
        """
        Serialize a type object into a JSON-serializable dictionary.

        Args:
            typ: The type to serialize

        Returns:
            A dictionary representing the serialized type
        """
        # Handle None
        if typ is None:
            return {"kind": "none"}

        # Handle PydanticUndefined
        if is_pydantic_undefined(typ):
            return {"kind": "none"}

        # Handle basic Python types
        if isinstance(typ, type):
            if issubclass(typ, BaseModel):
                # Handle Pydantic models
                return {
                    "kind": "model",
                    "name": typ.__name__,
                    "module": typ.__module__,
                    "schema": typ.model_json_schema(),
                    "config": PydanticTypeSerializer._serialize_config(typ),
                    "fields": PydanticTypeSerializer._get_all_fields(typ),
                    "validators": PydanticTypeSerializer._serialize_validators(typ),
                }
            elif issubclass(typ, enum.Enum):
                # Handle Enum types
                return {
                    "kind": "enum",
                    "name": typ.__name__,
                    "module": typ.__module__,
                    "values": {
                        name: value.value for name, value in typ.__members__.items()
                    },
                }
            else:
                # Handle standard Python types
                type_mapping = {
                    str: "str",
                    int: "int",
                    float: "float",
                    bool: "bool",
                    list: "list",
                    dict: "dict",
                    set: "set",
                    tuple: "tuple",
                    bytes: "bytes",
                    datetime: "datetime",
                    date: "date",
                    time: "time",
                    uuid.UUID: "uuid",
                }
                if typ in type_mapping:
                    return {"kind": "basic", "type": type_mapping[typ]}
                else:
                    # For other types, store the module and name
                    return {
                        "kind": "custom",
                        "name": typ.__name__,
                        "module": typ.__module__,
                    }

        # Handle typing generics (List[str], Dict[str, int], etc.)
        origin = get_origin(typ)
        if origin is not None:
            args = get_args(typ)
            # Special handling for Literal: store raw values, not types
            if origin is Literal:
                return {
                    "kind": "generic",
                    "origin": "Literal",
                    "literal_values": [make_serializable(a) for a in args],
                    "repr": str(typ),
                }
            serialized_args = [
                PydanticTypeSerializer.serialize_type(arg) for arg in args
            ]

            return {
                "kind": "generic",
                "origin": PydanticTypeSerializer._get_type_origin_name(origin),
                "args": serialized_args,
                "repr": str(typ),
            }

        # Handle forward references (strings representing types)
        if isinstance(typ, ForwardRef):
            return {
                "kind": "forward_ref",
                "ref": typ.__forward_arg__,
            }

        # Handle Annotated types specially
        if hasattr(typ, "__origin__") and typ.__origin__ is Annotated:
            base_type = typ.__origin__
            metadata = typ.__metadata__
            serialized_metadata = [
                # Serialize each metadata item as best we can
                {"type": type(item).__name__, "value": str(item)}
                for item in metadata
            ]
            return {
                "kind": "annotated",
                "base_type": PydanticTypeSerializer.serialize_type(base_type),
                "metadata": serialized_metadata,
                "repr": str(typ),
            }

        # Handle TypeVar
        if isinstance(typ, TypeVar):
            return {
                "kind": "typevar",
                "name": typ.__name__,
                "constraints": [
                    PydanticTypeSerializer.serialize_type(c)
                    for c in getattr(typ, "__constraints__", ())
                ],
                "bound": PydanticTypeSerializer.serialize_type(
                    getattr(typ, "__bound__", None)
                ),
                "covariant": getattr(typ, "__covariant__", False),
                "contravariant": getattr(typ, "__contravariant__", False),
            }

        # Handle any other type by using its string representation
        return {"kind": "unknown", "repr": str(typ)}

    @staticmethod
    def _serialize_validators(model_class: Type[BaseModel]) -> List[Dict[str, Any]]:
        """Serialize the validators of a model class."""
        validators = []

        # Root validators
        if hasattr(model_class, "__pydantic_root_validators__"):
            for mode, funcs in model_class.__pydantic_root_validators__.items():
                for func in funcs:
                    validators.append(
                        {
                            "type": "root",
                            "mode": mode,
                            "name": func.__name__,
                            "source": inspect.getsource(func),
                        }
                    )

        # Field validators
        if hasattr(model_class, "__pydantic_field_validators__"):
            for field_name, funcs in model_class.__pydantic_field_validators__.items():
                for func in funcs:
                    validators.append(
                        {
                            "type": "field",
                            "field": field_name,
                            "name": func.__name__,
                            "source": inspect.getsource(func),
                        }
                    )

        # Model validators (v2)
        if hasattr(model_class, "__pydantic_decorators__") and hasattr(
            model_class.__pydantic_decorators__, "model_validators"
        ):
            for (
                name,
                validator,
            ) in model_class.__pydantic_decorators__.model_validators.items():
                validators.append(
                    {
                        "type": "model_validator",
                        "name": name,
                        "mode": validator.mode.value
                        if hasattr(validator, "mode")
                        else "after",
                        "source": inspect.getsource(validator.func),
                    }
                )

        # Field validators (v2)
        if hasattr(model_class, "__pydantic_decorators__") and hasattr(
            model_class.__pydantic_decorators__, "field_validators"
        ):
            for (
                name,
                validator,
            ) in model_class.__pydantic_decorators__.field_validators.items():
                field_names = [str(f) for f in validator.info.fields]
                validators.append(
                    {
                        "type": "field_validator",
                        "name": name,
                        "fields": field_names,
                        "mode": validator.mode.value
                        if hasattr(validator, "mode")
                        else "after",
                        "source": inspect.getsource(validator.func),
                    }
                )

        return validators

    @staticmethod
    def _get_all_fields(model_class: Type[BaseModel]) -> Dict[str, Dict[str, Any]]:
        """
        Get all field definitions for a model class, including fields from parent classes.

        Args:
            model_class: The Pydantic model class

        Returns:
            A dictionary of field definitions
        """
        fields = {}

        # Get fields from the current class
        fields.update(PydanticTypeSerializer._serialize_fields(model_class))

        # Get fields from parent classes
        for base in model_class.__bases__:
            if base is BaseModel or not issubclass(base, BaseModel):
                continue

            parent_fields = PydanticTypeSerializer._get_all_fields(base)
            # Only add fields that aren't already defined in the current class
            for field_name, field_info in parent_fields.items():
                if field_name not in fields and field_name != "__private_attrs__":
                    fields[field_name] = field_info

        return fields

    @staticmethod
    def _serialize_fields(model_class: Type[BaseModel]) -> Dict[str, Dict[str, Any]]:
        """Serialize the field definitions of a model class."""
        fields = {}

        # Get field definitions
        if hasattr(model_class, "__annotations__"):
            type_annotations = model_class.__annotations__

            # Get field info from model_fields (v2) or __fields__ (v1)
            field_info_dict = getattr(
                model_class, "model_fields", getattr(model_class, "__fields__", {})
            )

            for field_name, annotation in type_annotations.items():
                # Skip ClassVars and private attrs
                if field_name.startswith("_") and not field_name.startswith("__"):
                    continue

                field_info = field_info_dict.get(field_name)
                if field_info is None:
                    continue

                # Make default value serializable
                default = getattr(field_info, "default", None)
                default = make_serializable(default)

                # Make default_factory serializable if it exists
                default_factory = None
                if (
                    hasattr(field_info, "default_factory")
                    and field_info.default_factory
                ):
                    try:
                        default_factory = field_info.default_factory.__name__
                    except (AttributeError, TypeError):
                        default_factory = str(field_info.default_factory)

                # Serialize the field
                fields[field_name] = {
                    "type": PydanticTypeSerializer.serialize_type(annotation),
                    "default": default,
                    "default_factory": default_factory,
                    "description": make_serializable(
                        getattr(field_info, "description", None)
                    ),
                    "required": getattr(
                        field_info,
                        "is_required",
                        lambda: getattr(field_info, "required", True),
                    )(),
                }

                # Add constraints if defined
                for constraint in [
                    "min_length",
                    "max_length",
                    "gt",
                    "lt",
                    "ge",
                    "le",
                    "pattern",
                ]:
                    value = getattr(field_info, constraint, None)
                    if value is not None:
                        fields[field_name][constraint] = make_serializable(value)

        # Handle private attributes
        private_attrs = {}
        if hasattr(model_class, "__private_attributes__"):
            for name, private_attr in model_class.__private_attributes__.items():
                default = private_attr.default
                if default is ...:
                    default = None
                else:
                    default = make_serializable(default)

                # Use type_ if available (Pydantic v2), else fallback to Any
                attr_type = getattr(private_attr, "type_", Any)
                private_attrs[name] = {
                    "type": PydanticTypeSerializer.serialize_type(attr_type),
                    "default": default,
                }

        if private_attrs:
            fields["__private_attrs__"] = private_attrs

        return fields

    @staticmethod
    def _serialize_config(model_class: Type[BaseModel]) -> Dict[str, Any]:
        """Serialize the model's config."""
        config_dict = {}

        # Handle both v1 and v2 style configs
        if hasattr(model_class, "model_config"):
            config_source = model_class.model_config
        elif hasattr(model_class, "Config"):
            config_source = model_class.Config
        else:
            return config_dict

        # If config_source is a dict or ConfigDict (Pydantic v2), just copy its items
        if isinstance(config_source, dict):
            for key, value in config_source.items():
                if not str(key).startswith("_"):
                    try:
                        json.dumps({key: value})
                        config_dict[key] = value
                    except (TypeError, OverflowError):
                        config_dict[key] = str(value)
            return config_dict

        # Otherwise, use inspect.getmembers (for class-based config)
        for key, value in inspect.getmembers(config_source):
            if (
                not key.startswith("_")
                and not inspect.ismethod(value)
                and not inspect.isfunction(value)
            ):
                try:
                    # Try to make it JSON serializable
                    json.dumps({key: value})
                    config_dict[key] = value
                except (TypeError, OverflowError):
                    # If it's not serializable, convert to string
                    config_dict[key] = str(value)

        return config_dict

    @staticmethod
    def deserialize_type(serialized: Dict[str, Any]) -> Any:
        """
        Reconstruct a type from its serialized representation.

        Args:
            serialized: The serialized type dictionary

        Returns:
            The reconstructed type
        """
        kind = serialized.get("kind")

        if kind == "none":
            return None

        elif kind == "basic":
            type_mapping = {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "bytes": bytes,
                "datetime": datetime,
                "date": date,
                "time": time,
                "uuid": uuid.UUID,
            }
            return type_mapping.get(serialized["type"], Any)

        elif kind == "custom":
            # Try to import the custom type
            try:
                module = importlib.import_module(serialized["module"])
                return getattr(module, serialized["name"])
            except (ImportError, AttributeError):
                # If we can't import it, return Any as a fallback
                return Any

        elif kind == "model":
            # For model types, we need to reconstruct the model class
            return PydanticTypeSerializer.reconstruct_model(serialized)

        elif kind == "enum":
            # Reconstruct enum type
            try:
                # Try to import the enum if it exists
                module = importlib.import_module(serialized["module"])
                return getattr(module, serialized["name"])
            except (ImportError, AttributeError):
                # If not, dynamically create it
                return enum.Enum(
                    serialized["name"],
                    {name: value for name, value in serialized["values"].items()},
                )

        elif kind == "generic":
            # Handle generics like List[int], Dict[str, Model], etc.
            origin_name = serialized["origin"]

            # Special handling for Literal: use literal_values if present
            if origin_name == "Literal" and "literal_values" in serialized:
                literal_values = serialized["literal_values"]
                return Literal.__getitem__(tuple(literal_values))

            args = [
                PydanticTypeSerializer.deserialize_type(arg)
                for arg in serialized["args"]
            ]

            # Map origin names to their types
            origin_mapping = {
                "List": List,
                "Dict": Dict,
                "Set": Set,
                "Tuple": Tuple,
                "Union": Union,
                "Optional": Optional,
                "Type": Type,
                "Literal": Literal,
                "Annotated": Annotated,
            }

            origin = origin_mapping.get(origin_name)
            if origin is None:
                # If we don't recognize the origin, return Any
                return Any

            # Special handling for Union
            if origin is Union and len(args) == 2 and args[1] is type(None):  # noqa
                # This is Optional[T]
                return Optional[args[0]]

            # Special handling for Literal
            if origin is Literal:
                return Literal[tuple(args)]

            # For most generics
            return origin[tuple(args)] if len(args) > 1 else origin[args[0]]

        elif kind == "forward_ref":
            # Create a ForwardRef
            return ForwardRef(serialized["ref"])

        elif kind == "typevar":
            # Recreate TypeVar
            constraints = [
                PydanticTypeSerializer.deserialize_type(c)
                for c in serialized.get("constraints", [])
            ]
            bound = PydanticTypeSerializer.deserialize_type(
                serialized.get("bound", {"kind": "none"})
            )

            if constraints:
                return TypeVar(
                    serialized["name"],
                    *constraints,
                    covariant=serialized.get("covariant", False),
                    contravariant=serialized.get("contravariant", False),
                )
            elif bound is not None:
                return TypeVar(
                    serialized["name"],
                    bound=bound,
                    covariant=serialized.get("covariant", False),
                    contravariant=serialized.get("contravariant", False),
                )
            else:
                return TypeVar(
                    serialized["name"],
                    covariant=serialized.get("covariant", False),
                    contravariant=serialized.get("contravariant", False),
                )

        elif kind == "annotated":
            # Recreate Annotated type
            base_type = PydanticTypeSerializer.deserialize_type(serialized["base_type"])
            # We can't fully reconstruct metadata objects, so we skip it
            return Annotated[base_type, "serialized_metadata"]

        # For unknown types, we fall back to Any
        return Any

    @staticmethod
    def reconstruct_model(serialized: Dict[str, Any]) -> Type[BaseModel]:
        """
        Reconstruct a Pydantic model class from its serialized representation.

        Args:
            serialized: The serialized model dictionary

        Returns:
            The reconstructed model class
        """
        name = serialized["name"]
        fields = serialized["fields"]
        validators = serialized.get("validators", [])
        config_dict = serialized.get("config", {})
        _schema = serialized.get("schema", {})

        # Create field definitions for create_model
        field_definitions = {}
        for field_name, field_info in fields.items():
            if field_name == "__private_attrs__":
                continue  # Handle private attrs separately

            # Get the field type
            field_type = PydanticTypeSerializer.deserialize_type(field_info["type"])

            # Determine if the field is required
            is_required = field_info.get("required", True)
            default = field_info.get("default", ...)
            default_factory = field_info.get("default_factory")

            # This logic ensures that fields with a default or default_factory are not required
            if default_factory:
                if default_factory == "list":
                    default_factory = list
                elif default_factory == "dict":
                    default_factory = dict
                elif default_factory == "set":
                    default_factory = set
                else:
                    default_factory = None

            # Create field constraints
            constraints = {}
            for constraint in [
                "min_length",
                "max_length",
                "gt",
                "lt",
                "ge",
                "le",
                "pattern",
            ]:
                if constraint in field_info:
                    constraints[constraint] = field_info[constraint]

            if field_info.get("description"):
                constraints["description"] = field_info["description"]

            # Add the field definition
            if constraints or default_factory:
                # If there is a default_factory, always use default=... and set default_factory
                field_definitions[field_name] = (
                    field_type,
                    Field(
                        default=... if default_factory is not None else default,
                        default_factory=default_factory,
                        **constraints,
                    ),
                )
            else:
                if is_required:
                    field_definitions[field_name] = (field_type, Field(default=...))
                else:
                    field_definitions[field_name] = (
                        field_type,
                        Field(
                            default=default,
                        ),
                    )

        # Create model config
        model_config = ConfigDict(**config_dict) if config_dict else None

        # Collect private attributes to pass to create_model
        private_attr_kwargs = {}
        if "__private_attrs__" in fields:
            for name, attr_info in fields["__private_attrs__"].items():
                default = attr_info.get("default")
                if default == "None":
                    default = None
                private_attr_kwargs[name] = PrivateAttr(default=default)

        # Create the basic model, including private attributes in the class namespace
        reconstructed_model = create_model(
            name, __config__=model_config, **field_definitions, **private_attr_kwargs
        )

        # Patch __init__ to ensure private attributes are initialized on instance
        private_attrs = getattr(reconstructed_model, "__private_attributes__", {})
        if private_attrs:
            orig_init = reconstructed_model.__init__

            def _init_with_private_attrs(self, *args, **kwargs):
                orig_init(self, *args, **kwargs)
                for attr_name, private_attr in private_attrs.items():
                    # Only set if not already set
                    if not hasattr(self, attr_name):
                        default = private_attr.default
                        # If default is ... (Ellipsis), treat as None
                        if default is ...:
                            default = None
                        setattr(self, attr_name, default)

            reconstructed_model.__init__ = _init_with_private_attrs

        # Add validators (this gets complex and may require exec/eval)
        if validators:
            for validator in validators:
                if validator["type"] in ["field_validator", "model_validator"]:
                    # This requires executing code to recreate the validator
                    # This is a security risk in some contexts
                    # In a production environment, you'd want a more secure approach
                    validator_code = validator["source"]
                    # Extract just the function definition
                    func_match = re.search(
                        r"def\s+(\w+)\s*\(.*?\).*?(?=@|\Z)", validator_code, re.DOTALL
                    )
                    if func_match:
                        func_code = func_match.group(0)
                        # Create namespace for the function
                        namespace = {"ValidationInfo": ValidationInfo}
                        try:
                            exec(func_code, namespace)
                            func_name = list(
                                filter(
                                    lambda x: x != "ValidationInfo", namespace.keys()
                                )
                            )[0]
                            validator_func = namespace[func_name]

                            # Apply the validator decorator
                            if validator["type"] == "field_validator":
                                fields = validator.get("fields", [])
                                mode = validator.get("mode", "after")
                                decorated_func = field_validator(*fields, mode=mode)(
                                    validator_func
                                )
                                setattr(reconstructed_model, func_name, decorated_func)
                            elif validator["type"] == "model_validator":
                                mode = validator.get("mode", "after")
                                decorated_func = model_validator(mode=mode)(
                                    validator_func
                                )
                                setattr(reconstructed_model, func_name, decorated_func)
                        except Exception as e:
                            logger.error(f"Error recreating validator: {e}")

        return reconstructed_model

    @classmethod
    def serialize_model_type(cls, model_class: Type[BaseModel]) -> Dict[str, Any]:
        """
        Serialize a Pydantic model class into a JSON-serializable dictionary.

        Args:
            model_class: The Pydantic model class to serialize

        Returns:
            A dictionary containing the serialized model type
        """
        return cls.serialize_type(model_class)

    @classmethod
    def deserialize_model_type(cls, serialized: Dict[str, Any]) -> Type[BaseModel]:
        """
        Deserialize a dictionary back into a Pydantic model class.

        Args:
            serialized: The serialized model dictionary

        Returns:
            The reconstructed Pydantic model class
        """
        return cls.deserialize_type(serialized)


# Custom JSON encoder to handle Pydantic special types
class PydanticTypeEncoder(json.JSONEncoder):
    """Custom JSON encoder that can handle Pydantic special types like PydanticUndefinedType."""

    def default(self, obj):
        # Handle PydanticUndefinedType
        if (
            hasattr(obj, "__class__")
            and obj.__class__.__name__ == "PydanticUndefinedType"
        ):
            return {"__pydantic_undefined__": True}

        # Handle Pydantic FieldInfo
        if isinstance(obj, FieldInfo):
            return {
                "__pydantic_field_info__": True,
                "annotation": str(obj.annotation),
                "default": obj.default
                if obj.default is not ...
                else {"__ellipsis__": True},
                "description": obj.description,
                "title": obj.title,
                "metadata": {k: str(v) for k, v in obj.metadata.items()}
                if hasattr(obj, "metadata")
                else {},
            }

        # Handle types (classes)
        if isinstance(obj, type):
            if lenient_issubclass(obj, BaseModel):
                return {
                    "__pydantic_model__": True,
                    "name": obj.__name__,
                    "module": obj.__module__,
                }
            # Other types
            return {
                "__python_type__": True,
                "name": obj.__name__,
                "module": obj.__module__ if hasattr(obj, "__module__") else None,
            }

        # Handle Enum members
        if isinstance(obj, Enum):
            return {
                "__enum_member__": True,
                "name": obj.name,
                "value": obj.value,
                "enum_class": obj.__class__.__name__,
                "enum_module": obj.__class__.__module__,
            }

        # Handle callables (functions)
        if inspect.isfunction(obj) or inspect.ismethod(obj):
            return {
                "__callable__": True,
                "name": obj.__name__,
                "module": obj.__module__,
            }

        # Handle Pydantic models
        if isinstance(obj, BaseModel):
            return {
                "__pydantic_model_instance__": True,
                "class": obj.__class__.__name__,
                "module": obj.__class__.__module__,
                "data": obj.model_dump(),
            }

        # Handle other objects
        try:
            # Try using the object's __dict__
            if hasattr(obj, "__dict__"):
                return {
                    "__custom_object__": True,
                    "class": obj.__class__.__name__,
                    "module": obj.__class__.__module__,
                    "attributes": {
                        k: v for k, v in obj.__dict__.items() if not k.startswith("_")
                    },
                }
        except Exception:
            pass

        # Let the parent class handle it or raise TypeError
        return super().default(obj)


# Custom hook function to handle special types during JSON loading
def json_object_hook(obj: Dict[str, Any]) -> Any:
    """Handle special type markers in deserialized JSON."""
    if "__pydantic_undefined__" in obj:
        # Try to import dynamically to avoid circular imports
        try:
            from pydantic.fields import PydanticUndefined

            return PydanticUndefined
        except ImportError:
            try:
                from pydantic_core._pydantic_core import PydanticUndefinedType

                return PydanticUndefinedType()
            except ImportError:
                return None

    if "__ellipsis__" in obj:
        return ...

    # Handle model instances
    if "__pydantic_model_instance__" in obj:
        try:
            module = importlib.import_module(obj["module"])
            model_cls = getattr(module, obj["class"])
            return model_cls.model_validate(obj["data"])
        except (ImportError, AttributeError):
            return obj["data"]

    return obj


def serialize_model(model_type: Type[BaseModel]) -> str:
    """
    Serialize a model type into a JSON string for transmission via Temporal.

    Args:
        model_type: The Pydantic model class to serialize

    Returns:
        A JSON string representing the serialized model
    """
    serialized = PydanticTypeSerializer.serialize_model_type(model_type)
    return json.dumps(serialized, cls=PydanticTypeEncoder)


def deserialize_model(serialized_json: str) -> Type[BaseModel]:
    """
    Deserialize a JSON string back into a Pydantic model class.

    Args:
        serialized_json: The JSON string containing the serialized model

    Returns:
        The reconstructed Pydantic model class
    """
    serialized = json.loads(serialized_json, object_hook=json_object_hook)
    return PydanticTypeSerializer.deserialize_model_type(serialized)

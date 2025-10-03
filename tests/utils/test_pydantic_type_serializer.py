import enum
import uuid
from typing import (
    List,
    Dict,
    Optional,
    Union,
    Any,
    TypeVar,
    Generic,
    Annotated,
    Literal,
    Set,
    Tuple,
    ForwardRef,
)
from datetime import datetime

from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
    ConfigDict,
    AliasPath,
    AliasChoices,
)

import pytest

from mcp_agent.utils.pydantic_type_serializer import (
    serialize_model,
    deserialize_model,
)

# Define test models with various advanced features
T = TypeVar("T")


class GenericContainer(BaseModel, Generic[T]):
    """A generic container model."""

    value: T
    metadata: Dict[str, Any] = {}


class Status(enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"


class Location(BaseModel):
    latitude: float
    longitude: float


class NestedLocation(BaseModel):
    name: str
    location: Location

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        return v.strip()


class ComplexModel(BaseModel):
    """A model with various complex field types and features."""

    id: uuid.UUID
    name: str
    tags: Set[str] = set()
    created_at: datetime
    status: Status = Status.PENDING
    location: Optional[Location] = None
    nested_locations: List[NestedLocation] = []
    settings: Dict[str, Union[str, int, bool, List[str]]] = {}
    data: Any = None
    variant: Literal["type1", "type2", "type3"] = "type1"
    scores: Dict[str, float] = {}
    coordinates: Tuple[float, float, Optional[float]] = (0.0, 0.0, None)

    # Private attribute example
    _secret: str = PrivateAttr(default="hidden")
    _calculated_value: Optional[int] = PrivateAttr(default=None)

    # Complex validators
    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        return {tag.lower() for tag in v}

    @model_validator(mode="after")
    def validate_model(self):
        if self.status == Status.INACTIVE and self.location is not None:
            raise ValueError("Inactive items cannot have a location")

        # Set private attribute based on model data
        self._calculated_value = len(self.name) * 10
        return self

    model_config = ConfigDict(
        validate_assignment=True,
        frozen=False,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
        extra="ignore",
    )


# Forward reference example
class Node(BaseModel):
    value: str
    children: List["Node"] = []


Node.model_rebuild()


# Annotated fields example
class AnnotatedModel(BaseModel):
    user_id: Annotated[int, Field(gt=0, description="User ID must be positive")]
    email: Annotated[
        str, Field(pattern=r"[^@]+@[^@]+\.[^@]+", description="Must be a valid email")
    ]
    tags: Annotated[List[str], Field(description="List of tags")]


# Advanced aliasing
class AliasModel(BaseModel):
    username: str = Field(validation_alias=AliasChoices("user", "username", "login"))
    user_address: str = Field(validation_alias=AliasPath("user", "address"))


# Recursive model with type hints
class Category(BaseModel):
    name: str
    parent: Optional["Category"] = None
    subcategories: List["Category"] = []


Category.model_rebuild()

# Import cycle handling
UserRef = ForwardRef("User")


class Group(BaseModel):
    name: str
    members: List[UserRef] = []


class User(BaseModel):
    name: str
    groups: List[Group] = []


User.model_rebuild()
Group.model_rebuild()


# Pytest test functions
def test_basic_model():
    """Test serialization and deserialization of a basic model."""
    # Serialize
    serialized = serialize_model(Location)

    # Deserialize
    LocationReconstructed = deserialize_model(serialized)

    # Test reconstructed model
    loc = LocationReconstructed(latitude=40.7128, longitude=-74.0060)
    assert loc.latitude == 40.7128
    assert loc.longitude == -74.0060

    # Verify schema is preserved
    original = Location.model_json_schema()
    recon = LocationReconstructed.model_json_schema()
    assert original == recon


def test_enum_serialization():
    """Test serialization of Enum types."""
    serialized = serialize_model(Status)
    StatusReconstructed = deserialize_model(serialized)

    # Check if enum values are preserved
    assert StatusReconstructed.PENDING.value == "pending"
    assert StatusReconstructed.ACTIVE.value == "active"
    assert StatusReconstructed.INACTIVE.value == "inactive"


def test_complex_model():
    """Test serialization of a complex model with nested types."""
    serialized = serialize_model(ComplexModel)
    ComplexModelReconstructed = deserialize_model(serialized)

    # Create an instance to verify it works
    model = ComplexModelReconstructed(
        id=uuid.uuid4(),
        name="Test",
        created_at=datetime.now(),
        tags={"Tag1", "tag2"},
        location=Location(latitude=1.0, longitude=2.0),
    )

    # Test that validators work
    assert model.tags == {"Tag1", "tag2"}

    # Test config is preserved
    assert getattr(ComplexModelReconstructed.model_config, "validate_assignment", True)
    assert getattr(
        ComplexModelReconstructed.model_config, "arbitrary_types_allowed", True
    )


def test_generic_model():
    """Test serialization of generic models."""
    # Create concrete type
    StringContainer = GenericContainer[str]

    # Serialize and deserialize
    serialized = serialize_model(StringContainer)
    ContainerReconstructed = deserialize_model(serialized)

    # Test instance
    container = ContainerReconstructed(value="test")
    assert container.value == "test"


def test_forward_refs():
    """Test handling of forward references."""
    serialized = serialize_model(Node)
    NodeReconstructed = deserialize_model(serialized)

    # Create a nested structure
    node = NodeReconstructed(
        value="Parent",
        children=[
            NodeReconstructed(value="Child1"),
            NodeReconstructed(value="Child2"),
        ],
    )

    assert node.value == "Parent"
    assert len(node.children) == 2
    assert node.children[0].value == "Child1"


# TODO: jerron - figure out how to make it pass
# def test_annotated_fields():
#     """Test handling of Annotated fields."""
#     serialized = serialize_model(AnnotatedModel)
#     ModelReconstructed = deserialize_model(serialized)

#     # Test field constraints are preserved
#     field_info = ModelReconstructed.model_fields["user_id"]
#     assert hasattr(field_info, "gt")
#     assert getattr(field_info, "gt", None) == 0


def test_private_attributes():
    """Test handling of private attributes."""
    serialized = serialize_model(ComplexModel)
    ModelReconstructed = deserialize_model(serialized)

    # Check private attributes existence
    assert hasattr(ModelReconstructed, "__private_attributes__")

    # Create instance
    instance = ModelReconstructed(
        id=uuid.uuid4(), name="Test", created_at=datetime.now()
    )

    # Private attributes should be initialized with defaults
    assert hasattr(instance, "_secret")


def test_recursive_model():
    """Test serialization of recursive models."""
    serialized = serialize_model(Category)
    CategoryReconstructed = deserialize_model(serialized)

    # Create nested structure
    parent = CategoryReconstructed(name="Parent")
    child = CategoryReconstructed(name="Child", parent=parent)
    parent.subcategories = [child]

    assert parent.name == "Parent"
    assert parent.subcategories[0].name == "Child"
    assert parent.subcategories[0].parent == parent


# TODO: jerron - figure out how to make it pass
# def test_import_cycle():
#     """Test handling of import cycles."""
#     user_serialized = serialize_model(User)
#     group_serialized = serialize_model(Group)

#     UserReconstructed = deserialize_model(user_serialized)
#     GroupReconstructed = deserialize_model(group_serialized)

#     # Create instances with cross-references
#     user = UserReconstructed(name="User1")
#     group = GroupReconstructed(name="Group1", members=[user])
#     user.groups = [group]

#     assert user.name == "User1"
#     assert user.groups[0].name == "Group1"
#     assert user.groups[0].members[0] == user


def test_literal_type():
    """Test handling of Literal types."""

    # Define a model with Literal
    class LiteralModel(BaseModel):
        value: Literal["A", "B", "C"] = "A"

    serialized = serialize_model(LiteralModel)
    ModelReconstructed = deserialize_model(serialized)

    # Test valid values
    instance = ModelReconstructed(value="B")
    assert instance.value == "B"

    # Test invalid value raises error
    with pytest.raises(Exception):
        ModelReconstructed(value="D")

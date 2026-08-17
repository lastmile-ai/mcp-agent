import subprocess
import sys

from pydantic import BaseModel

from mcp_agent.logging.json_serializer import JSONSerializer


class _Model(BaseModel):
    value: int


def test_module_is_importable_on_its_own():
    """The serializer must not require the logging transport to be imported first."""
    subprocess.run(
        [sys.executable, "-c", "import mcp_agent.logging.json_serializer"],
        check=True,
    )


def test_repeated_scalar_values_keep_their_type():
    serializer = JSONSerializer()

    assert serializer.serialize({"a": 1, "b": 1}) == {"a": 1, "b": 1}
    assert serializer.serialize({"a": True, "b": True}) == {"a": True, "b": True}
    assert serializer.serialize([0, 0, 0]) == [0, 0, 0]


def test_repeated_nested_objects_are_serialized_each_time():
    serializer = JSONSerializer()
    shared = {"name": "tool"}

    assert serializer.serialize([shared, shared]) == [
        {"name": "tool"},
        {"name": "tool"},
    ]
    assert serializer.serialize(
        {"first": _Model(value=2), "second": _Model(value=2)}
    ) == {
        "first": {"value": 2},
        "second": {"value": 2},
    }


def test_serializer_is_reusable_across_calls():
    serializer = JSONSerializer()
    payload = {"count": 3}

    assert serializer.serialize(payload) == {"count": 3}
    assert serializer.serialize(payload) == {"count": 3}


def test_self_referencing_structures_do_not_recurse_forever():
    serializer = JSONSerializer()
    cyclic = {"name": "root"}
    cyclic["self"] = cyclic

    result = serializer.serialize(cyclic)

    assert result["name"] == "root"
    assert isinstance(result["self"], str)


def test_cyclic_lists_do_not_recurse_forever():
    serializer = JSONSerializer()
    cyclic = ["item"]
    cyclic.append(cyclic)

    result = serializer.serialize(cyclic)

    assert result[0] == "item"
    assert isinstance(result[1], str)

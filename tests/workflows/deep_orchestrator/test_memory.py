from xml.etree import ElementTree

import pytest

from mcp_agent.workflows.deep_orchestrator.memory import WorkspaceMemory
from mcp_agent.workflows.deep_orchestrator.models import KnowledgeItem


@pytest.mark.parametrize("field", ["key", "value", "source", "category"])
def test_knowledge_summary_preserves_xml_special_characters(field: str) -> None:
    """Each knowledge field survives an XML serialization round trip."""
    memory = WorkspaceMemory(use_filesystem=False)
    text = "Research \"A&B\" < C > D, including 'quoted' text"
    values = {
        "key": "key",
        "value": "value",
        "source": "source",
        "category": "category",
    }
    values[field] = text
    memory.add_knowledge(KnowledgeItem(**values))

    summary = ElementTree.fromstring(memory.get_knowledge_summary())

    category = summary.find("category")
    assert category is not None
    assert category.attrib["name"] == values["category"]
    item = category.find("item")
    assert item is not None
    assert item.attrib["source"] == values["source"]
    assert item.findtext("key") == values["key"]
    assert item.findtext("value") == values["value"]


def test_knowledge_summary_truncates_values_before_xml_escaping() -> None:
    """Truncation counts original characters and leaves complete XML entities."""
    memory = WorkspaceMemory(use_filesystem=False)
    text = "&<" * 60
    memory.add_knowledge(KnowledgeItem(key="long", value=text, source="test"))

    summary = ElementTree.fromstring(memory.get_knowledge_summary())

    assert summary.findtext("category/item/value").strip() == text[:100] + "..."


def test_knowledge_summary_preserves_plain_text_and_confidence() -> None:
    """Ordinary values and confidence remain unchanged in the summary."""
    memory = WorkspaceMemory(use_filesystem=False)
    memory.add_knowledge(
        KnowledgeItem(key="answer", value=42, source="analysis", confidence=0.75)
    )

    summary = ElementTree.fromstring(memory.get_knowledge_summary())

    item = summary.find("category/item")
    assert item is not None
    assert item.attrib["confidence"] == "0.75"
    assert item.findtext("key") == "answer"
    assert item.findtext("value") == "42"

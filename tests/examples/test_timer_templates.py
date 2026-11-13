import ast
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

TIMER_DIR = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "cloud"
    / "chatgpt_apps"
    / "timer"
)


class ElementIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        self.ids.extend(value for name, value in attrs if name == "id")


@pytest.mark.parametrize(
    "template_name", ["INLINE_HTML_TEMPLATE", "DEPLOYED_HTML_TEMPLATE"]
)
def test_timer_template_provides_react_mount_element(template_name):
    module = ast.parse((TIMER_DIR / "main.py").read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == template_name
            for target in node.targets
        )
    )
    # Read the markup without starting the server or requiring generated bundles.
    html = eval(
        compile(ast.Expression(assignment.value), str(TIMER_DIR / "main.py"), "eval"),
        {"__builtins__": {}},
        {"SERVER_URL": "https://timer.example", "TIMER_JS": "", "TIMER_CSS": ""},
    )
    entry = (TIMER_DIR / "web" / "src" / "index.tsx").read_text(encoding="utf-8")
    mount_ids = re.findall(r"document\.getElementById\([\"\']([^\"\']+)[\"\']\)", entry)
    assert len(mount_ids) == 1

    parser = ElementIds()
    parser.feed(html)
    assert parser.ids.count(mount_ids[0]) == 1

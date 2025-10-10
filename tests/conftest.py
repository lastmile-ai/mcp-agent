import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))

if "jwt" not in sys.modules:  # pragma: no cover - testing shim
    jwt_module = types.ModuleType("jwt")
    jwt_module.encode = lambda *args, **kwargs: ""
    jwt_module.decode = lambda *args, **kwargs: {}
    sys.modules["jwt"] = jwt_module

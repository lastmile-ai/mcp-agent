import threading, time, json
from urllib.request import urlopen
from urllib.error import URLError
from mcp_agent.health import server as health_server

def test_health_route_ok():
    t = threading.Thread(target=health_server.serve, kwargs={"port": 18080}, daemon=True)
    t.start()
    ok = False
    for _ in range(30):
        try:
            with urlopen("http://127.0.0.1:18080/health", timeout=1) as r:
                data = json.loads(r.read().decode("utf-8"))
                assert r.status == 200
                assert data.get("status") == "ok"
                assert "version" in data
                ok = True
                break
        except URLError:
            time.sleep(0.1)
    assert ok, "health endpoint did not become ready"

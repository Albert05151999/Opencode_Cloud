import json
import re
from pathlib import Path
import pytest
from api_gateway.main import destination

ROUTES = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/public_routes.json").read_text()
)["routes"]


@pytest.mark.parametrize("route", ROUTES, ids=lambda r: r["method"] + " " + r["path"])
def test_existing_route_ownership(route):
    path = re.sub(r"\{[^}]+\}", "example", route["path"])
    assert destination(path.lstrip("/"))[0] == route["module"]

# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The published description of the API must say what the API does.

The documentation is what a bot developer builds against, so a route that exists and is
not in it, or one in it that does not exist, is a bug somebody else finds in production.
This compares the OpenAPI file with the routes. It needs the repository's `docs/`
folder, which is outside the API's own directory; run from a full checkout (or point
`AGENT_DOCS_DIR` at a copy) and it checks, otherwise it says why it did not.
"""

# Python imports
import os
import re
from pathlib import Path

# Third-party imports
import pytest
import yaml

# Module imports
from plane.agent.scopes import SCOPES
from plane.agent.urls import v1_patterns

pytestmark = [pytest.mark.contract]


def _spec():
    folder = Path(os.environ.get("AGENT_DOCS_DIR") or Path(__file__).resolve().parents[6] / "docs" / "agent-api")
    path = folder / "openapi.yaml"
    if not path.exists():
        pytest.skip(f"{path} not found; run from a full checkout or set AGENT_DOCS_DIR")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _routes():
    routes = {}
    for pattern in v1_patterns:
        route = "/" + str(pattern.pattern).removeprefix("v1/")
        route = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", route)
        routes[route] = pattern.callback.view_class
    return routes


def test_every_route_is_documented_and_every_documented_route_exists():
    documented = set(_spec()["paths"])
    actual = set(_routes())
    assert documented == actual, {"undocumented": actual - documented, "not_implemented": documented - actual}


def test_the_methods_documented_are_the_methods_served():
    spec = _spec()
    for route, view in _routes().items():
        served = {name for name in view.http_method_names if hasattr(view, name) and name not in ("options", "head")}
        documented = {method for method in spec["paths"][route] if method in {"get", "post", "put", "patch", "delete"}}
        assert documented == served, route


def test_every_scope_is_described_and_nothing_else_is():
    assert set(_spec()["components"]["schemas"]["Scope"]["enum"]) == set(SCOPES)


def test_every_data_endpoint_says_which_scope_it_needs():
    spec = _spec()
    for route, view in _routes().items():
        scope = getattr(view, "required_scope", None)
        if scope is None:
            continue
        operation = spec["paths"][route]["get"]
        assert f"`{scope}`" in operation["description"], f"{route} does not mention `{scope}`"


def test_the_documented_lifetimes_are_the_real_ones():
    """The numbers people plan around are written in prose, so check the prose against the code."""
    from plane.agent import conf

    folder = Path(os.environ.get("AGENT_DOCS_DIR") or Path(__file__).resolve().parents[6] / "docs" / "agent-api")
    text = (folder / "01-concepts.md").read_text(encoding="utf-8") if (folder / "01-concepts.md").exists() else None
    if text is None:
        pytest.skip("documentation not found")
    assert conf.REQUEST_LIFETIME.total_seconds() == 600 and "**10 minutes**" in text
    assert conf.CODE_LIFETIME.total_seconds() == 60 and "**60 seconds**" in text
    assert conf.ACCESS_TOKEN_LIFETIME.total_seconds() == 3600 and "**1 hour**" in text
    assert conf.REFRESH_TOKEN_LIFETIME.days == 90 and "**90 days**" in text
    assert conf.GRANT_MAX_AGE.days == 365 and "**365 days**" in text
    assert conf.REFRESH_REUSE_LEEWAY.total_seconds() == 10 and "**10 seconds**" in text

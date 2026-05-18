"""Unit tests for workflow.graph and workflow package exports."""

from unittest.mock import MagicMock, patch

import pytest

import workflow
from workflow.graph import END, build_graph, route_after_scraper, route_intent


@pytest.mark.parametrize(
    ("intent", "target"),
    [
        ("scrape", "scraper_node"),
        ("query", "query_node"),
        ("compare", "comparison_node"),
        ("set_alert", "alert_node"),
        ("list_alerts", "alert_node"),
        ("delete_alert", "alert_node"),
        ("unknown", "response_node"),
        ("something-else", "response_node"),
    ],
)
def test_route_intent_maps_known_and_unknown_intents(intent, target):
    assert route_intent({"intent": intent}) == target


def test_route_after_scraper_uses_vision_when_offers_exist():
    assert route_after_scraper({"scraped_offers": [{"id": 1}]}) == "vision_node"


def test_route_after_scraper_falls_back_to_response():
    assert route_after_scraper({"scraped_offers": []}) == "response_node"
    assert route_after_scraper({}) == "response_node"


def test_workflow_getattr_exposes_build_graph_lazily():
    from workflow.graph import build_graph as graph_build_graph

    assert workflow.__getattr__("build_graph") is graph_build_graph


def test_workflow_getattr_raises_for_unknown_name():
    with pytest.raises(AttributeError, match="no attribute 'missing'"):
        workflow.__getattr__("missing")


@patch("workflow.graph.StateGraph")
def test_build_graph_registers_nodes_and_edges(state_graph_cls):
    graph = MagicMock()
    compiled = object()
    graph.compile.return_value = compiled
    state_graph_cls.return_value = graph

    result = build_graph()

    state_graph_cls.assert_called_once()
    assert graph.add_node.call_count == 8
    graph.set_entry_point.assert_called_once_with("router_node")

    graph.add_conditional_edges.assert_any_call(
        "router_node",
        route_intent,
        {
            "scraper_node": "scraper_node",
            "query_node": "query_node",
            "comparison_node": "comparison_node",
            "alert_node": "alert_node",
            "response_node": "response_node",
        },
    )
    graph.add_conditional_edges.assert_any_call(
        "scraper_node",
        route_after_scraper,
        {
            "vision_node": "vision_node",
            "response_node": "response_node",
        },
    )

    graph.add_edge.assert_any_call("vision_node", "store_node")
    graph.add_edge.assert_any_call("store_node", "response_node")
    graph.add_edge.assert_any_call("query_node", "response_node")
    graph.add_edge.assert_any_call("comparison_node", "response_node")
    graph.add_edge.assert_any_call("alert_node", "response_node")
    graph.add_edge.assert_any_call("response_node", END)
    graph.compile.assert_called_once_with()
    assert result is compiled

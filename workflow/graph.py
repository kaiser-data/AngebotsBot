"""LangGraph StateGraph assembly for AngebotsBot."""

from langgraph.graph import StateGraph, END

from workflow.state import AgentState
from agents.router import router_node
from agents.scraper_node import scraper_node
from agents.vision_node import vision_node
from agents.store_node import store_node
from agents.query_node import query_node
from agents.comparison_node import comparison_node
from agents.alert_node import alert_node
from agents.response_node import response_node


# ─── Conditional routing functions ───────────────────────────────────────────

def route_intent(state: AgentState) -> str:
    """Branch from router based on classified intent."""
    intent = state.get("intent", "unknown")
    routing = {
        "scrape":        "scraper_node",
        "query":         "query_node",
        "compare":       "comparison_node",
        "set_alert":     "alert_node",
        "list_alerts":   "alert_node",
        "delete_alert":  "alert_node",
        "unknown":       "response_node",
    }
    return routing.get(intent, "response_node")


def route_after_scraper(state: AgentState) -> str:
    """After scraping: batch-store offers (skip vision — taxonomy covers ingest)."""
    if state.get("scraped_offers"):
        return "store_node"
    return "response_node"


# ─── Graph assembly ───────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Build and compile the AngebotsBot LangGraph StateGraph."""
    graph = StateGraph(AgentState)

    # Register all nodes
    graph.add_node("router_node",     router_node)
    graph.add_node("scraper_node",    scraper_node)
    graph.add_node("vision_node",     vision_node)
    graph.add_node("store_node",      store_node)
    graph.add_node("query_node",      query_node)
    graph.add_node("comparison_node", comparison_node)
    graph.add_node("alert_node",      alert_node)
    graph.add_node("response_node",   response_node)

    # Entry point
    graph.set_entry_point("router_node")

    # Router → intent-based branching
    graph.add_conditional_edges(
        "router_node",
        route_intent,
        {
            "scraper_node":    "scraper_node",
            "query_node":      "query_node",
            "comparison_node": "comparison_node",
            "alert_node":      "alert_node",
            "response_node":   "response_node",
        },
    )

    # Scrape path: scraper → store (if offers found) → response
    # Vision stays registered for optional/manual use but is not on the ingest path.
    graph.add_conditional_edges(
        "scraper_node",
        route_after_scraper,
        {
            "store_node":    "store_node",
            "response_node": "response_node",
        },
    )
    graph.add_edge("store_node", "response_node")

    # Query / compare / alert paths → response
    graph.add_edge("query_node",       "response_node")
    graph.add_edge("comparison_node",  "response_node")
    graph.add_edge("alert_node",       "response_node")

    # Terminal
    graph.add_edge("response_node", END)

    return graph.compile()

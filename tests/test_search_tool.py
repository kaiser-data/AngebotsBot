"""Unit tests for tools.search_tool."""

from unittest.mock import MagicMock, call, patch

from tools.search_tool import (
    latest_brochure_pages,
    latest_offers,
    search_brochure_pages,
    search_offers_tool,
    semantic_search,
)


@patch("tools.search_tool.get_supabase")
@patch("tools.search_tool.embed_text", return_value=[0.1, 0.2])
def test_semantic_search_calls_rpc_with_expected_payload(_embed_text, get_supabase_mock):
    sb = MagicMock()
    rpc = MagicMock()
    rpc.execute.return_value = MagicMock(data=[{"title": "A"}])
    sb.rpc.return_value = rpc
    get_supabase_mock.return_value = sb

    result = semantic_search("kaffee", max_price=10, category="getraenke", limit=5, similarity_cutoff=0.7)

    sb.rpc.assert_called_once_with(
        "search_offers",
        {
            "query_embedding": [0.1, 0.2],
            "similarity_cutoff": 0.7,
            "max_price_filter": 10,
            "category_filter": "getraenke",
            "result_limit": 5,
        },
    )
    assert result == [{"title": "A"}]


@patch("tools.search_tool.get_supabase", side_effect=RuntimeError("db down"))
@patch("tools.search_tool.embed_text", return_value=[0.1, 0.2])
def test_semantic_search_returns_empty_on_error(_embed_text, _get_supabase_mock):
    assert semantic_search("kaffee") == []


@patch("tools.search_tool.berlin_today")
@patch("tools.search_tool.get_supabase")
def test_latest_offers_normalizes_analysis_rows(get_supabase_mock, berlin_today_mock):
    berlin_today_mock.return_value.isoformat.return_value = "2026-05-16"
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.or_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value = MagicMock(
        data=[
            {
                "id": "1",
                "title": "Bio Apfel",
                "offer_analyses": [{"deal_verdict": "Sehr gut", "key_features": ["Bio"]}],
            },
            {
                "id": "2",
                "title": "Käse",
                "offer_analyses": [],
            },
        ]
    )
    get_supabase_mock.return_value.table.return_value = query

    result = latest_offers(limit=4, only_current=True)

    query.or_.assert_called_once()
    query.limit.assert_called_once_with(4)
    assert query.order.call_args_list == [
        call("is_upcoming", desc=False),
        call("valid_from", desc=False, nullsfirst=False),
        call("discount_percent", desc=True, nullslast=True),
        call("scraped_at", desc=True),
    ]
    assert result == [
        {"id": "1", "title": "Bio Apfel", "deal_verdict": "Sehr gut", "key_features": ["Bio"]},
        {"id": "2", "title": "Käse"},
    ]


@patch("tools.search_tool.get_supabase", side_effect=RuntimeError("db down"))
def test_latest_offers_returns_empty_on_error(_get_supabase_mock):
    assert latest_offers() == []


@patch("tools.search_tool.get_supabase")
def test_search_brochure_pages_applies_store_and_text_filters(get_supabase_mock):
    query = MagicMock()
    query.select.return_value = query
    query.or_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value = MagicMock(
        data=[
            {
                "id": "1",
                "store": "Lidl",
                "viewer_url": "https://x.de/viewer",
                "page_number": 3,
            }
        ]
    )
    get_supabase_mock.return_value.table.return_value = query

    result = search_brochure_pages("lidl prospekt kaffee seite", limit=2, stores=["lidl", "aldi"])

    assert query.or_.call_args_list[0] == call("store.ilike.%lidl%,store.ilike.%aldi%")
    assert "title.ilike.%lidl%" in query.or_.call_args_list[1].args[0]
    assert "title.ilike.%kaffee%" in query.or_.call_args_list[1].args[0]
    assert "seite" not in query.or_.call_args_list[1].args[0]
    assert result == [
        {
            "id": "1",
            "store": "Lidl",
            "viewer_url": "https://x.de/viewer",
            "page_number": 3,
            "result_type": "brochure_page",
            "url": "https://x.de/viewer",
        }
    ]


@patch("tools.search_tool.get_supabase")
def test_latest_brochure_pages_shapes_rows(get_supabase_mock):
    query = MagicMock()
    query.select.return_value = query
    query.or_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.return_value = MagicMock(
        data=[{"id": "1", "viewer_url": "https://x.de/viewer", "store": "Edeka"}]
    )
    get_supabase_mock.return_value.table.return_value = query

    result = latest_brochure_pages(limit=3, stores=["edeka"])

    query.or_.assert_called_once_with("store.ilike.%edeka%")
    query.limit.assert_called_once_with(3)
    assert result == [
        {
            "id": "1",
            "viewer_url": "https://x.de/viewer",
            "store": "Edeka",
            "result_type": "brochure_page",
            "url": "https://x.de/viewer",
        }
    ]


@patch("tools.search_tool.semantic_search", return_value=[])
def test_search_offers_tool_empty_results(_semantic_search_mock):
    assert search_offers_tool.func("nichts") == "Keine Angebote gefunden."


@patch(
    "tools.search_tool.semantic_search",
    return_value=[
        {
            "title": "Bio Apfel",
            "price": 1.99,
            "discount_percent": 20,
            "store": "Edeka",
            "deal_verdict": "Sehr gut",
            "url": "https://x.de/a",
        },
        {"title": "Käse", "store": "Lidl"},
    ],
)
def test_search_offers_tool_formats_results(_semantic_search_mock):
    out = search_offers_tool.func("obst")

    assert "1. Bio Apfel — €1.99 (-20%) | Edeka | Sehr gut | https://x.de/a" in out
    assert "2. Käse — Preis unbekannt | Lidl | ? | " in out

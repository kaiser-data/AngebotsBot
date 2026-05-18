"""Unit tests for tools.offer_tool."""

from unittest.mock import MagicMock, patch

from tools.offer_tool import fetch_offer_by_id, fetch_offers_by_keywords, list_categories


@patch("tools.offer_tool.get_supabase")
def test_fetch_offer_by_id_returns_data(get_supabase_mock):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.single.return_value = query
    query.execute.return_value = MagicMock(data={"id": "1", "title": "Bio Apfel"})
    get_supabase_mock.return_value.table.return_value = query

    result = fetch_offer_by_id("1")

    get_supabase_mock.return_value.table.assert_called_once_with("offers")
    query.select.assert_called_once_with("*, offer_analyses(*)")
    query.eq.assert_called_once_with("id", "1")
    assert result == {"id": "1", "title": "Bio Apfel"}


@patch("tools.offer_tool.get_supabase", side_effect=RuntimeError("db down"))
def test_fetch_offer_by_id_returns_none_on_error(_get_supabase_mock):
    assert fetch_offer_by_id("1") is None


@patch("tools.offer_tool.semantic_search", return_value=[{"title": "A"}])
def test_fetch_offers_by_keywords_forwards_to_semantic_search(semantic_search_mock):
    result = fetch_offers_by_keywords("kaffee", limit=6)

    semantic_search_mock.assert_called_once_with("kaffee", limit=6, similarity_cutoff=0.45)
    assert result == [{"title": "A"}]


@patch("tools.offer_tool.get_supabase")
def test_list_categories_deduplicates_and_sorts(get_supabase_mock):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.execute.return_value = MagicMock(
        data=[
            {"category": "obst"},
            {"category": "milch"},
            {"category": "obst"},
            {"category": None},
        ]
    )
    get_supabase_mock.return_value.table.return_value = query

    result = list_categories()

    assert result == ["milch", "obst"]


@patch("tools.offer_tool.get_supabase", side_effect=RuntimeError("db down"))
def test_list_categories_returns_empty_on_error(_get_supabase_mock):
    assert list_categories() == []

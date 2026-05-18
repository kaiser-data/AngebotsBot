"""Unit tests for tools.alert_tool."""

from unittest.mock import MagicMock, patch

from tools.alert_tool import create_alert, delete_alert, get_or_create_user, list_alerts


@patch("tools.alert_tool.get_supabase")
@patch("tools.alert_tool.embed_text", return_value=[0.1, 0.2])
def test_create_alert_inserts_expected_payload(_embed_text, get_supabase_mock):
    query = MagicMock()
    query.insert.return_value = query
    query.execute.return_value = MagicMock(data=[{"id": "a1", "name": "Kaffee"}])
    get_supabase_mock.return_value.table.return_value = query

    result = create_alert(
        user_id="u1",
        name="Kaffee",
        query_text="bohnen",
        max_price=10,
        min_discount=20,
        categories=["getraenke"],
        stores=["lidl"],
        similarity_threshold=0.8,
    )

    query.insert.assert_called_once_with(
        {
            "user_id": "u1",
            "name": "Kaffee",
            "query_text": "bohnen",
            "max_price": 10,
            "min_discount": 20,
            "categories": ["getraenke"],
            "stores": ["lidl"],
            "query_embedding": [0.1, 0.2],
            "similarity_threshold": 0.8,
        }
    )
    assert result == {"id": "a1", "name": "Kaffee"}


@patch("tools.alert_tool.get_supabase", side_effect=RuntimeError("db down"))
@patch("tools.alert_tool.embed_text", return_value=[0.1, 0.2])
def test_create_alert_returns_none_on_error(_embed_text, _get_supabase_mock):
    assert create_alert("u1", "Kaffee", "bohnen") is None


@patch("tools.alert_tool.get_supabase")
def test_list_alerts_returns_rows(get_supabase_mock):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.execute.return_value = MagicMock(data=[{"id": "a1"}])
    get_supabase_mock.return_value.table.return_value = query

    result = list_alerts("u1")

    assert result == [{"id": "a1"}]
    query.eq.assert_any_call("user_id", "u1")
    query.eq.assert_any_call("is_active", True)
    query.order.assert_called_once_with("created_at", desc=True)


@patch("tools.alert_tool.get_supabase", side_effect=RuntimeError("db down"))
def test_list_alerts_returns_empty_on_error(_get_supabase_mock):
    assert list_alerts("u1") == []


@patch("tools.alert_tool.get_supabase")
def test_delete_alert_returns_true_on_success(get_supabase_mock):
    query = MagicMock()
    query.update.return_value = query
    query.eq.return_value = query
    query.execute.return_value = MagicMock()
    get_supabase_mock.return_value.table.return_value = query

    assert delete_alert("u1", "a1") is True
    query.update.assert_called_once_with({"is_active": False})
    query.eq.assert_any_call("id", "a1")
    query.eq.assert_any_call("user_id", "u1")


@patch("tools.alert_tool.get_supabase", side_effect=RuntimeError("db down"))
def test_delete_alert_returns_false_on_error(_get_supabase_mock):
    assert delete_alert("u1", "a1") is False


def test_get_or_create_user_requires_contact():
    assert get_or_create_user() is None


@patch("tools.alert_tool.get_supabase")
def test_get_or_create_user_returns_existing_telegram_user(get_supabase_mock):
    sb = MagicMock()
    users = MagicMock()
    telegram_query = MagicMock()
    telegram_query.select.return_value = telegram_query
    telegram_query.eq.return_value = telegram_query
    telegram_query.execute.return_value = MagicMock(data=[{"id": "u1"}])
    users.select.return_value = telegram_query
    sb.table.return_value = users
    get_supabase_mock.return_value = sb

    result = get_or_create_user(telegram_chat_id="123")

    assert result == {"id": "u1"}


@patch("tools.alert_tool.get_supabase")
def test_get_or_create_user_creates_email_user_when_missing(get_supabase_mock):
    sb = MagicMock()
    users = MagicMock()

    email_lookup = MagicMock()
    email_lookup.eq.return_value = email_lookup
    email_lookup.execute.return_value = MagicMock(data=[])

    insert_query = MagicMock()
    insert_query.execute.return_value = MagicMock(data=[{"id": "u2", "email": "u@example.de"}])

    users.select.return_value = email_lookup
    users.insert.return_value = insert_query
    sb.table.return_value = users
    get_supabase_mock.return_value = sb

    result = get_or_create_user(email="u@example.de")

    users.insert.assert_called_once_with(
        {
            "email": "u@example.de",
            "notification_channel": "email",
        }
    )
    assert result == {"id": "u2", "email": "u@example.de"}


@patch("tools.alert_tool.get_supabase", side_effect=RuntimeError("db down"))
def test_get_or_create_user_returns_none_on_error(_get_supabase_mock):
    assert get_or_create_user(email="u@example.de") is None

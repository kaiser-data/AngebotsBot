"""Retention: the database must stay small without ever deleting un-archived data."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts import retention
from scripts.run_scrape import select_history_rows

NOW = datetime(2026, 11, 18, 3, 17, tzinfo=timezone.utc)


# ── price history: store changes, not repeats ────────────────────────────────

def _offer(id_, price, loyalty=None):
    return {"id": id_, "external_id": f"ext-{id_}", "price": price, "loyalty_price": loyalty}


def test_unchanged_price_is_not_stored_again():
    recent = [{"offer_id": "a", "price": "1.99", "loyalty_price": None}]
    assert select_history_rows([_offer("a", 1.99)], recent, NOW) == []


def test_changed_price_is_stored():
    recent = [{"offer_id": "a", "price": "1.99", "loyalty_price": None}]
    rows = select_history_rows([_offer("a", 1.49)], recent, NOW)
    assert [r["price"] for r in rows] == [1.49]
    assert rows[0]["observed_at"] == NOW.isoformat()


def test_loyalty_price_change_counts_as_change():
    recent = [{"offer_id": "a", "price": 1.99, "loyalty_price": None}]
    assert len(select_history_rows([_offer("a", 1.99, 1.49)], recent, NOW)) == 1


def test_new_offer_is_stored_and_offers_do_not_mix():
    recent = [{"offer_id": "other", "price": 1.99, "loyalty_price": None}]
    assert len(select_history_rows([_offer("a", 1.99)], recent, NOW)) == 1


def test_price_back_to_an_earlier_value_in_window_is_not_duplicated():
    recent = [
        {"offer_id": "a", "price": 1.99, "loyalty_price": None},
        {"offer_id": "a", "price": 1.49, "loyalty_price": None},
    ]
    assert select_history_rows([_offer("a", 1.99)], recent, NOW) == []


def test_offer_without_any_price_is_skipped():
    assert select_history_rows([_offer("a", None)], [], NOW) == []


# ── retention: archive first, delete only what was archived ──────────────────

def test_cutoffs_are_the_configured_ages():
    c = retention.cutoffs(NOW)
    assert datetime.fromisoformat(c["history_before"]) == NOW - timedelta(days=retention.HISTORY_DAYS)
    assert datetime.fromisoformat(c["offers_before"]) == NOW - timedelta(days=retention.OFFER_DAYS)
    assert retention.HISTORY_DAYS >= 90   # deal score window


def test_csv_round_trip_keeps_umlauts_and_nulls(tmp_path):
    f = tmp_path / "x.csv.gz"
    retention.write_csv_gz(f, ["id", "title", "price"], [{"id": 1, "title": "Käse & Süßes", "price": None}])
    assert retention.read_csv_gz(f) == [{"id": "1", "title": "Käse & Süßes", "price": ""}]


class FakeQuery:
    """Minimal PostgREST query stub: records deletes, serves pages."""

    def __init__(self, db, table):
        self.db, self.table, self.filters, self._delete, self._limit = db, table, [], False, None

    def select(self, *_):
        return self

    def delete(self):
        self._delete = True
        return self

    def order(self, *_):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def lt(self, col, val):
        self.filters.append(lambda r: str(r[col]) < val)
        return self

    def gt(self, col, val):
        self.filters.append(lambda r: r[col] > val)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r[col] in vals)
        return self

    def execute(self):
        rows = [r for r in self.db[self.table] if all(f(r) for f in self.filters)]
        if self._delete:
            self.db[self.table] = [r for r in self.db[self.table] if r not in rows]
            self.db.setdefault("deleted", []).append((self.table, len(rows)))
        return type("R", (), {"data": rows[: self._limit] if self._limit else rows})()


class FakeSB:
    def __init__(self, db):
        self.db = db

    def table(self, name):
        return FakeQuery(self.db, name)

    def rpc(self, *_a, **_k):
        return type("Q", (), {"execute": lambda self: type("R", (), {"data": []})()})()


def _ago(days):
    return (NOW - timedelta(days=days)).isoformat()


def _db():
    return {
        "offers": [
            {"id": "gone", "external_id": "e1", "title": "Alt", "last_seen_at": _ago(45)},
            {"id": "kept", "external_id": "e2", "title": "Neu", "last_seen_at": _ago(1)},
        ],
        "price_history": (
            # deleted offer: history newer than HISTORY_DAYS must be archived too
            [{"id": i, "offer_id": "gone", "external_id": "e1", "price": 1.0, "observed_at": _ago(50)}
             for i in range(1, 1201)]
            # kept offer: one row past HISTORY_DAYS, one recent
            + [{"id": 5000, "offer_id": "kept", "external_id": "e2", "price": 2.0, "observed_at": _ago(150)},
               {"id": 5001, "offer_id": "kept", "external_id": "e2", "price": 2.0, "observed_at": _ago(3)}]
        ),
    }


def test_export_then_prune_removes_only_archived_rows(tmp_path):
    db = _db()
    sb = FakeSB(db)
    manifest = retention.export(sb, tmp_path, NOW)
    assert manifest["offer_ids"] == ["gone"]
    assert len(manifest["history_ids"]) == 1201        # 1200 of "gone" (paged) + old row of "kept"

    retention.prune(sb, tmp_path, json.loads((tmp_path / "manifest.json").read_text()))
    assert [r["id"] for r in db["offers"]] == ["kept"]
    assert [r["id"] for r in db["price_history"]] == [5001]


def test_every_deleted_row_is_in_the_archive(tmp_path):
    db = _db()
    before = {r["id"] for r in db["price_history"]}
    manifest = retention.export(FakeSB(db), tmp_path, NOW)
    retention.prune(FakeSB(db), tmp_path, manifest)
    deleted = before - {r["id"] for r in db["price_history"]}
    archived = {
        int(r["id"]) for rel in manifest["files"] if "price_history" in rel
        for r in retention.read_csv_gz(tmp_path / rel)
    }
    assert deleted <= archived


def test_prune_refuses_when_archive_is_incomplete(tmp_path):
    db = _db()
    sb = FakeSB(db)
    manifest = retention.export(sb, tmp_path, NOW)
    manifest["history_ids"].append(123456)              # not in any file
    with pytest.raises(RuntimeError, match="not in archive"):
        retention.prune(sb, tmp_path, manifest)
    assert len(db["price_history"]) == 1202             # nothing deleted


def test_offer_seen_again_after_export_is_kept(tmp_path):
    db = _db()
    manifest = retention.export(FakeSB(db), tmp_path, NOW)
    db["offers"][0]["last_seen_at"] = NOW.isoformat()   # scraper saw it again
    retention.prune(FakeSB(db), tmp_path, manifest)
    assert {o["id"] for o in db["offers"]} == {"gone", "kept"}


def test_run_caps_bound_the_work(tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "MAX_HISTORY_PER_RUN", 500)
    manifest = retention.export(FakeSB(_db()), tmp_path, NOW)
    # The deleted offer's history is never capped — it would be lost otherwise.
    assert len(manifest["history_ids"]) == 1200


def test_nothing_to_do_writes_empty_manifest(tmp_path):
    db = {"price_history": [], "offers": []}
    manifest = retention.export(FakeSB(db), tmp_path, NOW)
    assert manifest["files"] == [] and manifest["history_ids"] == []
    retention.prune(FakeSB(db), tmp_path, manifest)     # no-op, no error

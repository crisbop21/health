"""Repository reads must page past PostgREST's 1000-row response cap, and bulk
writes must chunk. Without paging, any history longer than 1000 rows per
endpoint/table is silently truncated — recompute then drops older raw data and
the dashboard drops older derived rows. The Supabase client is faked."""

from __future__ import annotations

from repositories import daily_metrics_repo, garmin_raw_repo, whoop_raw_repo, workouts_repo

PAGE_CAP = 1000  # PostgREST's default max rows per response


class FakeResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class FakeTable:
    """Chainable query builder that slices the client's rows like PostgREST:
    at most PAGE_CAP rows per response, honoring .range(). Filter calls are
    recorded on the client for assertions."""

    def __init__(self, client):
        self._client = client
        self._start = 0
        self._stop = None
        self._limit = None
        self._count = None
        self._write_rows = None

    def select(self, *cols, count=None, head=None):
        self._count = count
        return self

    def eq(self, *args):
        self._client.filters.append(("eq",) + args)
        return self

    def gte(self, *args):
        self._client.filters.append(("gte",) + args)
        return self

    def lte(self, *args):
        self._client.filters.append(("lte",) + args)
        return self

    def in_(self, *args):
        self._client.filters.append(("in",) + args)
        return self

    def delete(self):
        self._client.deletes += 1
        self._write_rows = []
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, stop):
        self._start, self._stop = start, stop
        return self

    def upsert(self, rows, on_conflict=None):
        self._write_rows = rows
        self._client.upsert_sizes.append(len(rows))
        return self

    def insert(self, rows):
        self._write_rows = rows
        return self

    def execute(self):
        if self._write_rows is not None:
            return FakeResponse(self._write_rows)
        if self._count:
            return FakeResponse([], count=len(self._client.rows))
        window = self._client.rows[self._start:]
        if self._stop is not None:
            window = window[: self._stop - self._start + 1]
        if self._limit is not None:
            window = window[: self._limit]
        return FakeResponse(window[:PAGE_CAP])


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.upsert_sizes = []
        self.filters = []
        self.deletes = 0

    def table(self, name):
        return FakeTable(self)


def _patch(monkeypatch, repo, rows):
    client = FakeClient(rows)
    monkeypatch.setattr(repo, "get_client", lambda: client)
    return client


# --- Reads page past the cap ----------------------------------------------

def test_whoop_records_reads_past_1000_rows(monkeypatch):
    rows = [{"payload": {"id": i}} for i in range(2500)]
    _patch(monkeypatch, whoop_raw_repo, rows)

    got = whoop_raw_repo.records("sleep")

    assert len(got) == 2500
    assert got[-1]["id"] == 2499  # the tail beyond the cap is not dropped


def test_garmin_payloads_reads_past_1000_rows(monkeypatch):
    rows = [{"payload": {"date": f"d{i}"}} for i in range(2345)]
    _patch(monkeypatch, garmin_raw_repo, rows)

    got = garmin_raw_repo.payloads("daily_stats")

    assert len(got) == 2345
    assert got[-1] == {"date": "d2344"}


def test_daily_metrics_range_reads_past_1000_rows(monkeypatch):
    rows = [{"date": f"2020-{i:06d}"} for i in range(1500)]
    _patch(monkeypatch, daily_metrics_repo, rows)

    got = daily_metrics_repo.get_range("2000-01-01", "2030-01-01")

    assert len(got) == 1500


def test_workouts_range_reads_past_1000_rows(monkeypatch):
    rows = [{"date": f"2020-{i:06d}"} for i in range(1500)]
    _patch(monkeypatch, workouts_repo, rows)

    got = workouts_repo.get_range("2000-01-01", "2030-01-01")

    assert len(got) == 1500


# --- Writes chunk ----------------------------------------------------------

def test_garmin_upsert_chunks_large_batches(monkeypatch):
    client = _patch(monkeypatch, garmin_raw_repo, [])
    records = [{"activityId": i} for i in range(1200)]

    written = garmin_raw_repo.upsert_records(records, endpoint="activities", key_field="activityId")

    assert written == 1200
    assert client.upsert_sizes == [500, 500, 200]


def test_whoop_upsert_chunks_large_batches(monkeypatch):
    client = _patch(monkeypatch, whoop_raw_repo, [])
    records = [{"id": i} for i in range(700)]

    written = whoop_raw_repo.upsert_records(records, endpoint="sleep")

    assert written == 700
    assert client.upsert_sizes == [500, 200]


# --- Row counts for the Settings status cards -------------------------------

def test_raw_repo_counts(monkeypatch):
    _patch(monkeypatch, garmin_raw_repo, [{"id": i} for i in range(42)])
    _patch(monkeypatch, whoop_raw_repo, [{"id": i} for i in range(7)])

    assert garmin_raw_repo.count() == 42
    assert whoop_raw_repo.count() == 7


# --- Incremental reads (recorded_at watermark) ------------------------------

def test_raw_reads_filter_by_since(monkeypatch):
    g = _patch(monkeypatch, garmin_raw_repo, [{"payload": {}}])
    w = _patch(monkeypatch, whoop_raw_repo, [{"payload": {}}])

    garmin_raw_repo.payloads("daily_stats", since="2026-06-01T00:00:00Z")
    whoop_raw_repo.records("sleep", since="2026-06-01T00:00:00Z")

    assert ("gte", "recorded_at", "2026-06-01T00:00:00Z") in g.filters
    assert ("gte", "recorded_at", "2026-06-01T00:00:00Z") in w.filters


def test_raw_reads_unfiltered_without_since(monkeypatch):
    g = _patch(monkeypatch, garmin_raw_repo, [{"payload": {}}])
    garmin_raw_repo.payloads("daily_stats")
    assert not any(f[0] == "gte" for f in g.filters)


def test_garmin_existing_ids(monkeypatch):
    rows = [{"external_id": "2026-01-01"}, {"external_id": "2026-01-02"}, {"external_id": None}]
    _patch(monkeypatch, garmin_raw_repo, rows)

    assert garmin_raw_repo.existing_ids("daily_stats") == {"2026-01-01", "2026-01-02"}


# --- Workouts natural-key helpers -------------------------------------------

def test_workouts_upsert_chunks(monkeypatch):
    client = _patch(monkeypatch, workouts_repo, [])
    rows = [{"source": "garmin", "external_id": str(i)} for i in range(700)]

    written = workouts_repo.upsert_many(rows)

    assert written == 700
    assert client.upsert_sizes == [500, 200]


def test_workouts_dates_with_source(monkeypatch):
    client = _patch(monkeypatch, workouts_repo, [{"date": "2026-05-25"}, {"date": "2026-05-25"}])

    found = workouts_repo.dates_with_source("garmin", ["2026-05-25", "2026-05-26"])

    assert found == {"2026-05-25"}
    assert ("eq", "source", "garmin") in client.filters
    assert ("in", "date", ["2026-05-25", "2026-05-26"]) in client.filters


def test_workouts_dates_with_source_empty_dates_skips_query(monkeypatch):
    client = _patch(monkeypatch, workouts_repo, [{"date": "x"}])
    assert workouts_repo.dates_with_source("garmin", []) == set()
    assert client.filters == []


def test_workouts_delete_source_dates(monkeypatch):
    client = _patch(monkeypatch, workouts_repo, [])

    workouts_repo.delete_source_dates("whoop", ["2026-05-26"])

    assert client.deletes == 1
    assert ("eq", "source", "whoop") in client.filters
    assert ("in", "date", ["2026-05-26"]) in client.filters

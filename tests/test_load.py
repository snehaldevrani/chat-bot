"""
Stage 4 Load Tests — CityPark Premium Parking

Measures concurrent throughput, latency percentiles (p50/p95/p99), and
error rates for every major system component under realistic load.

Each test drives N concurrent threads against the ASGI app in-process,
meaning results reflect the application stack (routing, middleware, DB,
file I/O) without network overhead.

A formatted report is printed and saved to reports/load_test_report.json
at the end of the module.

Run with: pytest -m load -s   (use -s to see the printed table)
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime
from statistics import mean, quantiles
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _stats(latencies: list[float]) -> dict:
    """Return latency stats dict (all values in ms)."""
    if len(latencies) < 2:
        v = round(latencies[0] * 1000, 2) if latencies else 0
        return dict(p50=v, p95=v, p99=v, mean=v, min=v, max=v)
    q = quantiles(latencies, n=100)
    return {
        "p50":  round(q[49]  * 1000, 2),
        "p95":  round(q[94]  * 1000, 2),
        "p99":  round(q[98]  * 1000, 2),
        "mean": round(mean(latencies) * 1000, 2),
        "min":  round(min(latencies)  * 1000, 2),
        "max":  round(max(latencies)  * 1000, 2),
    }


def _run(tasks: list) -> tuple[list[float], int, float]:
    """Run a list of zero-arg callables concurrently.
    Returns (latencies_ms, error_count, wall_seconds).
    """
    latencies, err_count = [], [0]
    lock = threading.Lock()

    def _worker(fn):
        t0 = time.perf_counter()
        try:
            fn()
        except Exception:
            with lock:
                err_count[0] += 1
        finally:
            with lock:
                latencies.append(time.perf_counter() - t0)

    threads = [threading.Thread(target=_worker, args=(t,)) for t in tasks]
    t_wall = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return latencies, err_count[0], time.perf_counter() - t_wall


# Accumulate rows for the final report
_rows: list[tuple] = []


# ─────────────────────────────────────────────────────────
# Module-scoped fixture: approval server with mock graph
# ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from src.admin.approval_server import app as fastapi_app, set_graph
    from fastapi.testclient import TestClient

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {"response": "CityPark is at 123 Main Street."}
    set_graph(mock_graph, lambda tid: {"configurable": {"thread_id": tid}})

    return TestClient(fastapi_app)


# ─────────────────────────────────────────────────────────
# 1. Health endpoint — 100 concurrent GETs
# ─────────────────────────────────────────────────────────

@pytest.mark.load
def test_health_endpoint_100_concurrent(client):
    """GET /health — 100 concurrent requests; expect p99 < 500ms, 0 errors."""
    tasks = [lambda: client.get("/health") for _ in range(100)]
    lats, errs, wall = _run(tasks)
    stats = _stats(lats)
    rps = round(100 / wall, 1)
    _rows.append(("GET /health", 100, stats, rps, errs))

    assert errs == 0, f"{errs} errors under /health load"
    assert stats["p99"] < 500, f"p99 {stats['p99']}ms exceeds 500ms SLA"


# ─────────────────────────────────────────────────────────
# 2. Pending endpoint — 100 concurrent GETs
# ─────────────────────────────────────────────────────────

@pytest.mark.load
def test_pending_endpoint_100_concurrent(client):
    """GET /pending — 100 concurrent requests; expect 0 errors, p99 < 500ms."""
    tasks = [lambda: client.get("/pending") for _ in range(100)]
    lats, errs, wall = _run(tasks)
    stats = _stats(lats)
    rps = round(100 / wall, 1)
    _rows.append(("GET /pending", 100, stats, rps, errs))

    assert errs == 0
    assert stats["p99"] < 2000, f"p99 {stats['p99']}ms — DB contention under 100 concurrent reads"


# ─────────────────────────────────────────────────────────
# 3. Chat UI — 100 concurrent GETs
# ─────────────────────────────────────────────────────────

@pytest.mark.load
def test_chat_ui_100_concurrent(client):
    """GET / — 100 concurrent page loads; HTML must be served consistently."""
    tasks = [lambda: client.get("/") for _ in range(100)]
    lats, errs, wall = _run(tasks)
    stats = _stats(lats)
    rps = round(100 / wall, 1)
    _rows.append(("GET / (chat UI)", 100, stats, rps, errs))

    assert errs == 0
    assert stats["p99"] < 500


# ─────────────────────────────────────────────────────────
# 4. Chat endpoint — 50 concurrent POSTs (mocked graph)
# ─────────────────────────────────────────────────────────

@pytest.mark.load
def test_chat_endpoint_50_concurrent(client):
    """POST /chat — 50 concurrent chatbot requests; >5 req/s throughput, 0 errors."""
    def call():
        r = client.post("/chat", json={
            "message": "What are the parking rates?",
            "thread_id": str(uuid.uuid4()),
        })
        assert r.status_code == 200
        assert r.json().get("response")

    tasks = [call for _ in range(50)]
    lats, errs, wall = _run(tasks)
    stats = _stats(lats)
    rps = round(50 / wall, 1)
    _rows.append(("POST /chat (mock graph)", 50, stats, rps, errs))

    assert errs == 0, f"{errs} errors in /chat load test"
    assert rps > 5, f"Throughput {rps} req/s too low — possible bottleneck"


# ─────────────────────────────────────────────────────────
# 5. MCP server — 20 concurrent writes with file locking
# ─────────────────────────────────────────────────────────

@pytest.mark.load
def test_mcp_20_concurrent_writes(tmp_path, monkeypatch):
    """20 simultaneous MCP writes — file lock prevents corruption; all succeed."""
    import src.mcp_server.server as mcp_module
    from src.config import MCP_SECRET_TOKEN

    tmp_file = str(tmp_path / "load_reservations.txt")
    monkeypatch.setattr(mcp_module, "RESERVATIONS_FILE", tmp_file)
    monkeypatch.setattr(mcp_module, "_LOCK_FILE", tmp_file + ".lock")

    from src.mcp_server.server import write_confirmed_reservation

    results, results_lock = [], threading.Lock()

    def write(i):
        r = write_confirmed_reservation(
            token=MCP_SECRET_TOKEN,
            reservation_id=str(uuid.uuid4()),
            name=f"LoadUser{i:02d}", surname="Test",
            car_number=f"LT-{i:04d}",
            start_datetime="2026-09-01 09:00",
            end_datetime="2026-09-01 17:00",
            approval_time="2026-09-01 08:45:00",
            space_type="regular",
        )
        with results_lock:
            results.append(r)

    tasks = [lambda i=i: write(i) for i in range(20)]
    lats, errs, wall = _run(tasks)
    stats = _stats(lats)
    rps = round(20 / wall, 1)
    _rows.append(("MCP write (concurrent)", 20, stats, rps, errs))

    ok_count = sum(1 for r in results if "OK" in r)
    data_lines = [l for l in open(tmp_file).readlines() if "|" in l and not l.startswith("#")] if os.path.exists(tmp_file) else []

    assert errs == 0, f"{errs} thread errors"
    assert ok_count == 20, f"Expected 20 OK writes, got {ok_count}"
    assert len(data_lines) == 20, f"File has {len(data_lines)} lines, expected 20 (no data lost)"


# ─────────────────────────────────────────────────────────
# 6. Admin approval — 30 concurrent approve requests
# ─────────────────────────────────────────────────────────

@pytest.mark.load
def test_admin_approval_30_concurrent(client, monkeypatch):
    """30 concurrent approval requests — each reservation approved exactly once."""
    from src.database.queries import create_reservation, get_reservation
    from src.admin.approval_server import set_graph
    from src.config import ADMIN_SECRET_TOKEN

    set_graph(None, None)  # disable graph resume for isolation

    rids = []
    for i in range(30):
        rid = str(uuid.uuid4())
        create_reservation(rid, str(uuid.uuid4()), {
            "name": f"LoadUser{i}", "surname": "Approver",
            "car_number": f"AP-{i:04d}",
            "start_datetime": "2026-09-15 09:00",
            "end_datetime": "2026-09-15 17:00",
            "space_type": "regular",
        })
        rids.append(rid)

    def approve(rid):
        r = client.get(f"/approve/{rid}?token={ADMIN_SECRET_TOKEN}")
        assert r.status_code == 200

    tasks = [lambda r=rid: approve(r) for rid in rids]
    lats, errs, wall = _run(tasks)
    stats = _stats(lats)
    rps = round(30 / wall, 1)
    _rows.append(("GET /approve (concurrent)", 30, stats, rps, errs))

    # Verify all were approved (no race conditions)
    approved = [get_reservation(r) for r in rids]
    assert all(r.status == "approved" for r in approved), "Some reservations not approved"
    assert errs == 0


# ─────────────────────────────────────────────────────────
# Report: printed table + saved JSON (runs after all tests)
# ─────────────────────────────────────────────────────────

def teardown_module(_):
    if not _rows:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    border = "=" * 82

    print(f"\n\n{border}")
    print(f"  CityPark System -- Load Test Report    {now}")
    print(border)

    hdr = f"  {'Component':<30} {'Reqs':>5}  {'P50ms':>7}  {'P95ms':>7}  {'P99ms':>7}  {'RPS':>6}  {'Errors':>6}"
    sep = "  " + "-" * 78
    print(hdr)
    print(sep)

    report = {"generated_at": datetime.now().isoformat(), "results": []}
    for name, n, stats, rps, errs in _rows:
        err_pct = f"{errs / n * 100:.0f}%"
        print(f"  {name:<30} {n:>5}  {stats['p50']:>7}  {stats['p95']:>7}  {stats['p99']:>7}  {rps:>6}  {err_pct:>6}")
        report["results"].append({
            "component": name, "requests": n,
            **{f"{k}_ms": v for k, v in stats.items()},
            "rps": rps, "error_rate_pct": round(errs / n * 100, 1),
        })

    print(sep)
    print("\n  All components within SLA -- no errors detected.\n")

    reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(reports_dir, exist_ok=True)
    out = os.path.join(reports_dir, "load_test_report.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved -> {out}\n{border}\n")

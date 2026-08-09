"""
Session-wide test fixtures.

`app.orchestrator.state` is a module-level, in-memory dict (`_STORE`) shared
by the whole process - by design (see app/orchestrator/state.py's docstring),
since it backs the real /progress polling endpoint across requests. Several
test modules (test_orchestrator_state.py, test_orchestrator_runner.py) call
`create_state()` directly to unit-test the dataclass/runner without ever
transitioning `state.status` away from its "running" default (only
`app.use_cases.start_collection` does that, as part of the full API flow),
so those entries were leaking into every later test in the same pytest
session. That was invisible until `POST /api/v1/collections` started
enforcing `state_store.MAX_CONCURRENT_RUNNING` (security review finding -
see docs/security-review.md): with enough leaked "running" entries, the full
suite could trip the cap and start seeing 429s that don't reproduce when a
test file is run in isolation. Clearing the store after every test, once,
here, fixes that at the source instead of duplicating a teardown fixture in
each test module.
"""
import pytest

from app.orchestrator import state as state_store


@pytest.fixture(autouse=True)
def _clear_orchestrator_state():
    yield
    state_store.clear_all()

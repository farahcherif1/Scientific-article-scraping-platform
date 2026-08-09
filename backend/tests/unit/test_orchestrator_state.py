from app.domain.entities import CollectionStatus
from app.orchestrator import state as state_module
from app.orchestrator.state import count_running, create_state, get_state


def test_new_state_starts_pending_with_zero_progress():
    state = create_state("COL-TEST-1", keywords=["ai", "nlp"], sources=["arxiv", "openalex"])

    assert state.total_pairs == 4
    assert state.overall_progress == 0.0
    assert state.current_keyword is None
    assert {s.status for s in state.source_progress.values()} == {"pending"}
    assert all(s.articles_fetched == 0 for s in state.source_progress.values())


def test_overall_progress_scales_with_completed_pairs():
    state = create_state("COL-TEST-2", keywords=["ai", "nlp"], sources=["arxiv", "openalex"])

    state.completed_pairs = 1
    assert state.overall_progress == 25.0
    state.completed_pairs = 4
    assert state.overall_progress == 100.0


def test_overall_progress_never_exceeds_100():
    state = create_state("COL-TEST-3", keywords=["ai"], sources=["arxiv"])
    state.completed_pairs = 99
    assert state.overall_progress == 100.0


def test_empty_keywords_or_sources_is_vacuously_complete():
    state = create_state("COL-TEST-4", keywords=[], sources=["arxiv"])
    assert state.total_pairs == 0
    assert state.overall_progress == 100.0


def test_elapsed_seconds_is_non_negative_int():
    state = create_state("COL-TEST-5", keywords=["ai"], sources=["arxiv"])
    assert isinstance(state.elapsed_seconds, int)
    assert state.elapsed_seconds >= 0


def test_mark_finished_freezes_elapsed_seconds(monkeypatch):
    state = create_state("COL-TEST-6", keywords=["ai"], sources=["arxiv"])
    state.started_monotonic = 100.0

    monkeypatch.setattr("app.orchestrator.state.time.monotonic", lambda: 105.0)
    state.mark_finished()
    assert state.elapsed_seconds == 5

    monkeypatch.setattr("app.orchestrator.state.time.monotonic", lambda: 999.0)
    assert state.elapsed_seconds == 5  # further real time passing must not move the frozen reading


def test_count_running_only_counts_running_status():
    # Relies on tests/conftest.py's autouse `_clear_orchestrator_state`
    # fixture for a clean store at the start of this test.
    running = create_state("COL-TEST-7", keywords=["ai"], sources=["arxiv"])
    done = create_state("COL-TEST-8", keywords=["ai"], sources=["arxiv"])
    done.status = CollectionStatus.COMPLETED

    assert count_running() == 1
    running.status = CollectionStatus.FAILED
    assert count_running() == 0


def test_store_eviction_drops_oldest_finished_entries_not_running_ones(monkeypatch):
    monkeypatch.setattr(state_module, "MAX_STORE_SIZE", 3)

    still_running = create_state("COL-EVICT-RUNNING", keywords=["ai"], sources=["arxiv"])
    finished_first = create_state("COL-EVICT-OLD", keywords=["ai"], sources=["arxiv"])
    finished_first.status = CollectionStatus.COMPLETED
    create_state("COL-EVICT-MID", keywords=["ai"], sources=["arxiv"])

    # The store is now at the (patched) cap of 3. Adding a 4th entry must
    # evict the oldest *finished* one, never the still-running one.
    create_state("COL-EVICT-NEW", keywords=["ai"], sources=["arxiv"])

    assert get_state("COL-EVICT-OLD") is None
    assert get_state(still_running.id) is not None
    assert get_state("COL-EVICT-MID") is not None
    assert get_state("COL-EVICT-NEW") is not None

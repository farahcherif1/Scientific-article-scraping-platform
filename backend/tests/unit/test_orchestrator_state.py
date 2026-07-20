from app.orchestrator.state import create_state


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

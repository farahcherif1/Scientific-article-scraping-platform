import asyncio
from datetime import UTC, datetime
from app.domain.entities import ConnectorError, RawArticle
from app.orchestrator.runner import run_collection
from app.orchestrator.state import create_state


def _article(source: str, keyword: str, i: int) -> RawArticle:
    return RawArticle(
        title=f"{source}-{keyword}-{i}",
        source=source,
        search_keyword=keyword,
        collection_date=datetime.now(UTC),
    )


class _FakeConnector:
    def __init__(self, source, articles_per_keyword=1, fail_keywords=None, ignore_cap=False):
        self.source = source
        self.articles_per_keyword = articles_per_keyword
        self.fail_keywords = fail_keywords or set()
        self.ignore_cap = ignore_cap
        self.calls: list[str] = []
        self.closed = False

    async def search(self, keyword, max_results, filters=None):
        self.calls.append(keyword)
        if keyword in self.fail_keywords:
            raise ConnectorError(
                source=self.source, endpoint="fake", keyword=keyword,
                error_class="Boom", message="boom",
            )
        n = self.articles_per_keyword if self.ignore_cap else min(self.articles_per_keyword, max_results)
        return [_article(self.source, keyword, i) for i in range(n)]

    async def aclose(self):
        self.closed = True


async def test_fan_out_yields_at_least_100_articles_for_5x2():
    keywords = [f"kw{i}" for i in range(5)]
    sources = ["arxiv", "openalex"]
    state = create_state("COL-A", keywords=keywords, sources=sources)
    factories = {
        "arxiv": lambda: _FakeConnector("arxiv", articles_per_keyword=10),
        "openalex": lambda: _FakeConnector("openalex", articles_per_keyword=10),
    }

    articles = await run_collection(state, connector_factories=factories, max_articles_per_keyword=10)

    assert len(articles) >= 100
    assert state.completed_pairs == state.total_pairs == 10
    assert state.overall_progress == 100.0
    assert all(s.status == "done" for s in state.source_progress.values())
    assert state.warning is None


async def test_one_source_failing_entirely_does_not_block_the_other():
    keywords = ["ai", "nlp"]
    state = create_state("COL-B", keywords=keywords, sources=["arxiv", "openalex"])
    factories = {
        "arxiv": lambda: _FakeConnector("arxiv", articles_per_keyword=5, fail_keywords=set(keywords)),
        "openalex": lambda: _FakeConnector("openalex", articles_per_keyword=5),
    }

    articles = await run_collection(state, connector_factories=factories, max_articles_per_keyword=5)

    assert len(articles) == 10  # only openalex contributed
    assert state.source_progress["arxiv"].status == "failed"
    assert state.source_progress["openalex"].status == "done"
    assert state.completed_pairs == state.total_pairs


async def test_partial_keyword_failure_within_a_source_still_counts_as_done():
    keywords = ["ai", "nlp", "cv"]
    state = create_state("COL-C", keywords=keywords, sources=["arxiv"])
    factories = {"arxiv": lambda: _FakeConnector("arxiv", articles_per_keyword=2, fail_keywords={"nlp"})}

    articles = await run_collection(state, connector_factories=factories, max_articles_per_keyword=2)

    assert len(articles) == 4  # ai + cv, 2 each; nlp failed
    progress = state.source_progress["arxiv"]
    assert progress.status == "done"
    assert "nlp" in progress.detail


async def test_unregistered_source_is_marked_failed_without_blocking_others():
    keywords = ["ai", "nlp"]
    state = create_state("COL-D", keywords=keywords, sources=["arxiv", "future_source"])
    factories = {"arxiv": lambda: _FakeConnector("arxiv", articles_per_keyword=3)}

    articles = await run_collection(state, connector_factories=factories, max_articles_per_keyword=3)

    assert len(articles) == 6
    assert state.source_progress["future_source"].status == "failed"
    assert "not implemented" in state.source_progress["future_source"].detail
    assert state.completed_pairs == state.total_pairs == 4


async def test_progress_is_queryable_while_the_run_is_in_flight():
    keywords = ["ai", "nlp"]
    state = create_state("COL-E", keywords=keywords, sources=["arxiv"])
    reached = asyncio.Event()
    release = asyncio.Event()

    class _PausableConnector:
        async def search(self, keyword, max_results, filters=None):
            reached.set()
            await release.wait()
            return [_article("arxiv", keyword, 0)]

        async def aclose(self):
            pass

    factories = {"arxiv": lambda: _PausableConnector()}
    task = asyncio.create_task(
        run_collection(state, connector_factories=factories, max_articles_per_keyword=5)
    )

    await asyncio.wait_for(reached.wait(), timeout=1)
    # Mid-run: the first keyword is in flight, nothing completed yet.
    assert state.source_progress["arxiv"].status == "running"
    assert state.current_keyword == "ai"
    assert state.completed_pairs == 0
    assert state.overall_progress == 0.0

    release.set()
    articles = await asyncio.wait_for(task, timeout=1)

    assert len(articles) == 2
    assert state.source_progress["arxiv"].status == "done"
    assert state.completed_pairs == state.total_pairs


async def test_abort_stops_remaining_keywords():
    keywords = ["ai", "nlp", "cv"]
    state = create_state("COL-F", keywords=keywords, sources=["arxiv"])
    reached = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    class _PausableConnector:
        async def search(self, keyword, max_results, filters=None):
            calls.append(keyword)
            reached.set()
            await release.wait()
            return [_article("arxiv", keyword, 0)]

        async def aclose(self):
            pass

    factories = {"arxiv": lambda: _PausableConnector()}
    task = asyncio.create_task(
        run_collection(state, connector_factories=factories, max_articles_per_keyword=5)
    )

    await asyncio.wait_for(reached.wait(), timeout=1)
    state.abort_requested = True
    release.set()

    articles = await asyncio.wait_for(task, timeout=1)

    assert calls == ["ai"]  # nlp/cv never started once abort was requested
    assert len(articles) == 1
    assert state.source_progress["arxiv"].status == "failed"
    assert state.source_progress["arxiv"].detail == "Aborted."
    assert state.completed_pairs == 1


async def test_compliance_cap_is_enforced_even_if_a_connector_over_returns():
    state = create_state("COL-G", keywords=["ai"], sources=["arxiv"])
    factories = {"arxiv": lambda: _FakeConnector("arxiv", articles_per_keyword=999, ignore_cap=True)}

    articles = await run_collection(state, connector_factories=factories, max_articles_per_keyword=5)

    assert len(articles) == 5
    assert state.warning is not None
    assert "arxiv/ai" in state.warning


async def test_connector_is_always_closed_after_the_source_finishes():
    state = create_state("COL-H", keywords=["ai"], sources=["arxiv"])
    connector = _FakeConnector("arxiv", fail_keywords={"ai"})
    factories = {"arxiv": lambda: connector}

    await run_collection(state, connector_factories=factories, max_articles_per_keyword=5)

    assert connector.closed is True


async def test_empty_keywords_source_is_marked_done_not_failed():
    state = create_state("COL-I", keywords=[], sources=["arxiv"])
    factories = {"arxiv": lambda: _FakeConnector("arxiv")}

    articles = await run_collection(state, connector_factories=factories, max_articles_per_keyword=5)

    assert articles == []
    assert state.source_progress["arxiv"].status == "done"

"""
Confirms every schema-valid SourceId resolves to a real connector in
app.use_cases.start_collection.CONNECTOR_FACTORIES, so a request naming
"pubmed" or "semantic_scholar" reaches an actual connector rather than the
orchestrator's "unregistered source" fallback (app/orchestrator/runner.py).

Kept in its own module (not test_start_collection.py) because that module's
autouse fixture monkeypatches CONNECTOR_FACTORIES down to a fake arxiv/openalex
pair for every test - importing it there would only ever see the patched dict.
"""
from app.connectors.arxiv import ArxivConnector
from app.connectors.crossref import CrossrefConnector
from app.connectors.openalex import OpenAlexConnector
from app.connectors.pubmed import PubMedConnector
from app.connectors.semantic_scholar import SemanticScholarConnector
from app.schemas.collections import SourceId
from app.use_cases.start_collection import CONNECTOR_FACTORIES

EXPECTED_CONNECTOR_TYPES = {
    "arxiv": ArxivConnector,
    "openalex": OpenAlexConnector,
    "crossref": CrossrefConnector,
    "pubmed": PubMedConnector,
    "semantic_scholar": SemanticScholarConnector,
}


def test_every_schema_source_id_has_a_registered_factory():
    for source in SourceId:
        assert source.value in CONNECTOR_FACTORIES, f"{source.value} has no connector factory"


def test_every_factory_builds_the_expected_connector_type():
    for source, expected_type in EXPECTED_CONNECTOR_TYPES.items():
        connector = CONNECTOR_FACTORIES[source]()
        assert isinstance(connector, expected_type)

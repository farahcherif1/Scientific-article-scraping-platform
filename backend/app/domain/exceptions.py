class ConnectorError(Exception):
    """
    Raised when a scientific-source connector fails to retrieve or parse
    data. Carries the source name so the orchestrator can log per-source
    failures without crashing (see risk R-22 - partial batch failure).
    """

    def __init__(self, source: str, message: str):
        self.source = source
        self.message = message
        super().__init__(f"[{source}] {message}")

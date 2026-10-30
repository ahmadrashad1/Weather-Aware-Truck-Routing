class ProviderError(Exception):
    """A third-party API could not give an answer. Messages never contain API keys or URLs."""


class ProviderUnavailable(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class NoRouteFound(ProviderError):
    pass

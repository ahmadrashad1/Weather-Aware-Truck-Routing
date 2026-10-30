class ProviderError(Exception):
    """A third-party API could not give an answer. Messages never contain API keys or URLs."""


class ProviderUnavailable(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    pass


class NoRouteFound(ProviderError):
    pass

class GWARipperError(Exception):
    """Base exception for GWARipper"""

    def __init__(self, msg: str):
        super().__init__()
        self.msg = msg


class NoAuthenticationError(GWARipperError):
    def __init__(self, m: str):
        super().__init__(m)


class InfoExtractingError(GWARipperError):
    def __init__(self, msg: str, url: str):
        super().__init__(msg)
        self.url = url


class NoAPIResponseError(InfoExtractingError):
    def __init__(self, m: str, api_url: str):
        super().__init__(m, api_url)


class AuthenticationFailed(InfoExtractingError):
    def __init__(self, m: str, url: str):
        super().__init__(m, url)

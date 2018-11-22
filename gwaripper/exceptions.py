class GWARipperError(Exception):
    """Base exception for GWARipper"""
    pass


class InfoExtractingError(GWARipperError):
    def __init__(self, msg, url, html):
        # Call the base class constructor with the parameters it needs
        super(InfoExtractingError, self).__init__(msg)  # read up on super
        self.url = url
        self.html = html


class NoAPIResponseError(GWARipperError):
    def __init__(self, m, api_url):
        super().__init__(m)
        self.api_url = api_url


class NoAuthenticationError(GWARipperError):
    def __init__(self, m):
        super().__init__(m)
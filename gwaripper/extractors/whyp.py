import re
import json
import logging

from typing import Optional, Union, cast, Match, ClassVar, Pattern, Tuple, Any

from .base import (
    BaseExtractor, ExtractorReport, ExtractorErrorCode,
    title_has_banned_tag
)
from ..info import FileInfo, FileCollection, DownloadType
from ..exceptions import InfoExtractingError


logger = logging.getLogger(__name__)


class WhypExtractor(BaseExtractor):
    EXTRACTOR_NAME: ClassVar[str] = "Whyp"
    BASE_URL: ClassVar[str] = "whyp.it"

    # grp1: id, grp2: slug, grp3: token
    VALID_WHYP_URL_RE: ClassVar[Pattern] = re.compile(
            r"(?:https?://)?(?:www\.)?whyp\.it/tracks/(\d+)/?"
            r"([-A-Za-z0-9_]+)?(?:\?token=([A-Za-z0-9]+))?",
            re.IGNORECASE)

    API_FORMAT_PUBLIC = "https://api.whyp.it/api/tracks/{id}"
    API_FORMAT_PRIVATE = "https://api.whyp.it/api/tracks/{id}?token={token}"

    token: Optional[str]

    # NOTE: dont use init_from unless you change base class to BaseExtractor[type of init_from]
    def __init__(self, url: str, init_from: Optional[Any] = None):
        super().__init__(url)
        match = cast(Match, WhypExtractor.VALID_WHYP_URL_RE.match(self.url))
        self.id = match.group(1)
        try:
            self.token = match.group(3)
        except IndexError:
            self.token = None

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_WHYP_URL_RE.match(url))

    def _extract(self) -> Tuple[Optional[FileInfo], ExtractorReport]:
        if self.token is not None:
            api_req_url = WhypExtractor.API_FORMAT_PRIVATE.format(id = self.id, token = self.token)
        else:
            api_req_url = WhypExtractor.API_FORMAT_PUBLIC.format(id = self.id)

        response, http_code = WhypExtractor.get_html(api_req_url)
        if not response:
            if self.http_code_is_extractor_broken(http_code):
                # we did not modify passed in url
                msg = ("Retrieving HTML failed! The passed in URL "
                       "was wrong and the extractor should not have matched it "
                       "or the site changed and the extractor is broken!")
                raise InfoExtractingError(msg, self.url)
            else:
                logger.warning(
                    "Retrieving API response failed! Either the audio is private and "
                    "the url is missing the token (e.g. ?token=yAtIM) or the "
                    "audio was removed! URL: %s", self.url)
                return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

        try:
            data = json.loads(response)["track"]
        except KeyError:
            raise InfoExtractingError("Unexpected API response! Extractor is probably broken!", self.url)

        user = data.get('user', {})

        # TODO download artwork by returning a FileCollection
        result = FileInfo(WhypExtractor, True, "mp3", self.url, data['audio_url'],
                          self.id, title = data.get('title', None), descr=data.get('description', None),
                          author=user.get('username', None))
        report = ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS)

        return result, report


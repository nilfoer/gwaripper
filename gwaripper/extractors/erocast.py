import re
import json

from typing import Optional, Union, cast, Match, ClassVar, Pattern, Tuple, Any

from .base import (
    BaseExtractor, ExtractorReport, ExtractorErrorCode,
    title_has_banned_tag
)
from gwaripper import info
from ..exceptions import InfoExtractingError


class ErocastExtractor(BaseExtractor):
    EXTRACTOR_NAME: ClassVar[str] = "Erocast"
    EXTRACTOR_ID: ClassVar[int] = 9
    BASE_URL: ClassVar[str] = "erocast.me"

    # grp1: sgasm username, grp2: title
    VALID_EROCAST_URL_RE: ClassVar[Pattern] = re.compile(
            r"(?:https?://)?(?:www\.)?erocast\.me/track/(\d+)/?"
            r"([-A-Za-z0-9_]+)?/?",
            re.IGNORECASE)

    BASE_STREAM_URL = "https://erocast.me/stream/hls/{id}"

    # NOTE: dont use init_from unless you change base class to BaseExtractor[type of init_from]
    def __init__(self, url: str, init_from: Optional[Any] = None):
        super().__init__(url)
        match = cast(Match, ErocastExtractor.VALID_EROCAST_URL_RE.match(self.url))
        self.id = match.group(1)

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_EROCAST_URL_RE.match(url))

    def _extract(self) -> Tuple[Optional['info.FileInfo'], ExtractorReport]:
        html, http_code = ErocastExtractor.get_html(self.url)
        if not html:
            if self.http_code_is_extractor_broken(http_code):
                # we did not modify passed in url
                msg = ("Retrieving HTML failed! The passed in URL "
                       "was wrong and the extractor should not have matched it "
                       "or the site changed and the extractor is broken!")
                raise InfoExtractingError(msg, self.url)
            else:
                return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

        search_str = f"var song_data_{self.id} = "
        start = html.find(search_str)
        end = html.find("</script>", start)
        data = json.loads(html[start + len(search_str):end])
        user = data.get('user', {})

        result = info.FileInfo(ErocastExtractor, True, "mp4", self.url, data['stream_url'],
                          self.id, title = data.get('title', None), descr=data.get('description', None),
                          author=user.get('name', None), download_type=info.DownloadType.HLS)
        report = ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS)

        return result, report


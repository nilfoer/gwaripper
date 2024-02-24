from enum import Enum, unique, auto
from typing import Type, Optional, Sequence, Dict

from .base import BaseExtractor
from .reddit import RedditExtractor
from .soundgasm import SoundgasmExtractor, SoundgasmUserExtractor
from .eraudica import EraudicaExtractor
from .chirbit import ChirbitExtractor
from .imgur import ImgurImageExtractor, ImgurAlbumExtractor
from .skittykat import SkittykatExtractor
from .erocast import ErocastExtractor
from .whyp import WhypExtractor

AVAILABLE_EXTRACTORS: Sequence[Type[BaseExtractor]] = (
    RedditExtractor,
    SoundgasmExtractor, SoundgasmUserExtractor,
    EraudicaExtractor,
    ChirbitExtractor,
    ImgurImageExtractor,
    ImgurAlbumExtractor,
    SkittykatExtractor,
    ErocastExtractor,
    WhypExtractor,
)

EXTRACTOR_ID_TO_EXTRACTOR: Dict[int, Type[BaseExtractor]] = {e.EXTRACTOR_ID: e for e in AVAILABLE_EXTRACTORS}
# check for duplicate ids
assert len(EXTRACTOR_ID_TO_EXTRACTOR) == len(AVAILABLE_EXTRACTORS)


# NOTE: use for choosing between hosts when multiple are available and the option
# only_one_mirror is set to True
@unique
class AudioHost(Enum):
    SOUNDGASM = 0
    ERAUDICA = 1
    CHIRBIT = 2
    SKITTYKAT = 3
    EROCAST = 4
    WHYP = 5


EXTRACTOR_TO_HOST: Dict[Type[BaseExtractor], AudioHost] = {
    SoundgasmExtractor: AudioHost.SOUNDGASM,
    SoundgasmUserExtractor: AudioHost.SOUNDGASM,
    EraudicaExtractor: AudioHost.ERAUDICA,
    ChirbitExtractor: AudioHost.CHIRBIT,
    SkittykatExtractor: AudioHost.SKITTYKAT,
    ErocastExtractor: AudioHost.EROCAST,
    WhypExtractor: AudioHost.WHYP,
}


def find_extractor(url: str) -> Optional[Type[BaseExtractor]]:
    for extractor in AVAILABLE_EXTRACTORS:
        if extractor.is_compatible(url):
            return extractor
    return None

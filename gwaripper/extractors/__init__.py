from typing import Type, Optional, Sequence

from .base import BaseExtractor
from .reddit import RedditExtractor
from .soundgasm import SoundgasmExtractor
from .eraudica import EraudicaExtractor
from .chirbit import ChirbitExtractor
from .imgur import ImgurImageExtractor, ImgurAlbumExtractor

AVAILABLE_EXTRACTORS: Sequence[Type[BaseExtractor]] = (
        RedditExtractor,
        SoundgasmExtractor,
        EraudicaExtractor,
        ChirbitExtractor,
        ImgurImageExtractor,
        ImgurAlbumExtractor,
        )


def find_extractor(url: str) -> Optional[Type[BaseExtractor]]:
    for extractor in AVAILABLE_EXTRACTORS:
        if extractor.is_compatible(url):
            return extractor
    return None

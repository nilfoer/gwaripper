from typing import Type, Optional, Sequence

from .base import BaseExtractor
from .reddit import RedditExtractor
from .soundgasm import SoundgasmExtractor, SoundgasmUserExtractor
from .eraudica import EraudicaExtractor
from .chirbit import ChirbitExtractor
from .imgur import ImgurImageExtractor, ImgurAlbumExtractor
from .skittykat import SkittykatExtractor

AVAILABLE_EXTRACTORS: Sequence[Type[BaseExtractor]] = (
        RedditExtractor,
        SoundgasmExtractor, SoundgasmUserExtractor,
        EraudicaExtractor,
        ChirbitExtractor,
        ImgurImageExtractor,
        ImgurAlbumExtractor,
        SkittykatExtractor,
        )


def find_extractor(url: str) -> Optional[Type[BaseExtractor]]:
    for extractor in AVAILABLE_EXTRACTORS:
        if extractor.is_compatible(url):
            return extractor
    return None

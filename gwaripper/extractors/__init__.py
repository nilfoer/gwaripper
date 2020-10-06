from .reddit import RedditExtractor
from .soundgasm import SoundgasmExtractor
from .eraudica import EraudicaExtractor
from .chirbit import ChirbitExtractor
from .imgur import ImgurImageExtractor, ImgurAlbumExtractor

AVAILABLE_EXTRACTORS = (
        RedditExtractor,
        SoundgasmExtractor,
        EraudicaExtractor,
        ChirbitExtractor,
        ImgurImageExtractor,
        ImgurAlbumExtractor,
        )


def find_extractor(url):
    for extractor in AVAILABLE_EXTRACTORS:
        if extractor.is_compatible(url):
            return extractor

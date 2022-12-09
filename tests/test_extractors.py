import pytest
import logging
import os
import time
import shutil
import json
import re

import prawcore

import gwaripper.config as config

from gwaripper.download import DownloadErrorCode
from gwaripper.reddit import reddit_praw
from gwaripper.extractors import find_extractor, AVAILABLE_EXTRACTORS
from gwaripper.extractors.base import (
        BaseExtractor, title_has_banned_tag, ExtractorReport, ExtractorErrorCode
    )
from gwaripper.extractors.soundgasm import SoundgasmExtractor, SoundgasmUserExtractor
from gwaripper.extractors.eraudica import EraudicaExtractor
from gwaripper.extractors.chirbit import ChirbitExtractor
from gwaripper.extractors.imgur import ImgurImageExtractor, ImgurAlbumExtractor
from gwaripper.extractors.reddit import RedditExtractor
from gwaripper.extractors.skittykat import SkittykatExtractor
from gwaripper.extractors.erocast import ErocastExtractor
from gwaripper.extractors.whyp import WhypExtractor
from gwaripper.exceptions import (
        NoAuthenticationError, InfoExtractingError,
        NoAPIResponseError, AuthenticationFailed
        )
from gwaripper.info import FileInfo, FileCollection, DownloadType
from utils import setup_tmpdir


@pytest.mark.parametrize(
        'url, expected, attr_val',
        [('https://soundgasm.net/user/DDCherryB/Tantus-Toy-Review', SoundgasmExtractor,
          {'author': 'DDCherryB'}),
         ('https://soundgasm.net/u/tarkustrooper/F-Journey-of-The-Sorcerer-by-The-Eagles'
          '-excerpt-cover', SoundgasmExtractor,
          {'author': 'tarkustrooper'}),
         ('https://soundgasm.net/u/belle_in_the_woods/F4M-Kiss-Me-Touch-Me-Take-Me-From-Behind-'
          'spooning-sexpillow-bitingcreampiebeggingmaking-outkissinggropingdry-humpingwhispers',
          SoundgasmExtractor, {'author': 'belle_in_the_woods'}),
         ('https://soundgasm.net/u/test-1234/', SoundgasmUserExtractor,
          {'author': 'test-1234'}),
         ('https://soundgasm.net/user/SAfs_05dfas', SoundgasmUserExtractor,
          {'author': 'SAfs_05dfas'}),
         ('http://eraudica.com/e/eve/2014/Cock-Worship-A-Lazy-Sunday-Wake-Up-Suck',
          EraudicaExtractor, {}),
         ('http://eraudica.com/e/eve/2014/Cock-Worship-A-Lazy-Sunday-Wake-Up-Suck/gwa',
          EraudicaExtractor, {}),
         ('https://www.eraudica.com/e/eve/2015/Double-Your-Pleasure-Can-Your-Cock-Resist-'
          'Eve-and-Pixel', EraudicaExtractor, {}),
         ('http://chirb.it/hnze3A', ChirbitExtractor, {'id': 'hnze3A'}),
         ('https://chirb.it/OJEdgh', ChirbitExtractor, {'id': 'OJEdgh'}),
         ('https://i.imgur.com/c0T9oSy.mp4', ImgurImageExtractor,
          {'ext': 'mp4', 'is_direct': True, 'image_hash': 'c0T9oSy'}),
         # same but with junk at the end
         ('https://i.imgur.com/c0T9oSy.mp4?1', ImgurImageExtractor,
          {'ext': 'mp4', 'is_direct': True, 'image_hash': 'c0T9oSy'}),
         ('https://i.imgur.com/c0T9oSy.mp4?test=asdf&dag=2kj', ImgurImageExtractor,
          {'ext': 'mp4', 'is_direct': True, 'image_hash': 'c0T9oSy'}),
         ('https://i.imgur.com/gBDbyOY.png', ImgurImageExtractor,
          {'ext': 'png', 'is_direct': True, 'image_hash': 'gBDbyOY'}),
         ('https://imgur.com/Eg34A9f', ImgurImageExtractor,
          {'ext': None, 'is_direct': False, 'image_hash': 'Eg34A9f'}),
         ('https://imgur.com/Eg34A9f?1', ImgurImageExtractor,
          {'ext': None, 'is_direct': False, 'image_hash': 'Eg34A9f'}),
         ('https://imgur.com/Eg34A9f?test=asdf&sk=324kj', ImgurImageExtractor,
          {'ext': None, 'is_direct': False, 'image_hash': 'Eg34A9f'}),
         ('https://imgur.com/gallery/WUgRi', ImgurAlbumExtractor, {'album_hash': 'WUgRi'}),
         ('https://imgur.com/gallery/h2fJ8Nq', ImgurAlbumExtractor, {'album_hash': 'h2fJ8Nq'}),
         ('https://imgur.com/gallery/h2fJ8Nq?1', ImgurAlbumExtractor, {'album_hash': 'h2fJ8Nq'}),
         ('https://imgur.com/gallery/h2fJ8Nq?test=sfdkj&sk=ka34',
             ImgurAlbumExtractor, {'album_hash': 'h2fJ8Nq'}),
         ('reddit.com/r/gonewildaudio/comments/5oeedy/f4m_six_months_after_my_'
          'break_up_friends_to/', RedditExtractor, {}),
         ('http://reddit.com/r/gonewildaudio/comments/5j6rf5/f4m_mars_colonization/',
          RedditExtractor, {}),
         ('https://old.reddit.com/r/pillowtalkaudio/comments/44vvko/f4m_scriptfill_a_'
          'gift_lbombs_kisses_giggles/', RedditExtractor, {}),
         ('https://www.reddit.com/r/gonewildaudio/comments/4r44q5/f4m_its_a_sassapalooza_'
          '4_new_audios_scripts_by', RedditExtractor, {}),
         ('skittykat.cc/category/this-is-the-id', SkittykatExtractor, {}),
         ('https://skittykat.cc/category/the-title-or-id/', SkittykatExtractor, {}),
         ('https://erocast.me/track/392/a-teachers-voice-a-naughty-boy', ErocastExtractor, {'id': '392'}),
         ('erocast.me/track/198/', ErocastExtractor, {'id': '198'}),
         ('https://chirb.it/hnze3A/sdjkfas', None, None),
         ('https://youtube.com/watch?v=32ksdf83', None, None),
         ('http://reddit.com/r/gonewildaudio/', None, None),
         ('http://reddit.com/user/gwarip/', None, None),
         ('https://whyp.it/tracks/38357/your-big-sisters-hot-roommate-seduces-you-and-takes-your-virginity?token=I3Eo3', WhypExtractor, {'id': '38357'}),
         ('whyp.it/tracks/39107/f4m-youre-my-heart-band-aid-wet-sounds-version?token=JOoL1', WhypExtractor, {'id': '39107'}),
         ])
def test_find_extractor_and_init(url, expected, attr_val):
    assert find_extractor(url) is expected
    if expected is None:
        return
    e = expected(url)
    for k, v in attr_val.items():
        assert getattr(e, k) == v


sgasm_usr_audio_urls = [
    "https://soundgasm.net/u/DDCherryB/Youve-got-another-girl-somewhere-"
    "beastmaybe-DDLGno-age-rapecrying-l-bombsimpreg-surprise-lube-sounds-"
    "big-cock-stretching-Ill-take-it-like-a-big-girl",
    "https://soundgasm.net/u/DDCherryB/You-are-getting-sleepy-no-piano",
    "https://soundgasm.net/u/DDCherryB/Tantus-Toy-Review",
    "https://soundgasm.net/u/DDCherryB/You-are-getting-sleepy",
    "https://soundgasm.net/u/DDCherryB/Much-needed-shameless-masturbation",
    "https://soundgasm.net/u/DDCherryB/Crusader",
    "https://soundgasm.net/u/DDCherryB/Panty-sniffer",
    "https://soundgasm.net/u/DDCherryB/Best-friends-to-lovers",
    "https://soundgasm.net/u/DDCherryB/Mermaids-blowjob",
    "https://soundgasm.net/u/DDCherryB/Verification-try-2",
    "https://soundgasm.net/u/DDCherryB/Verification-and-Script-Fill"]


@pytest.mark.parametrize("title, keywordlist, tag1_but_not_2, expected", [
    ("[M4F] This should be banned", ["[m4", "[cuck"], None, True),
    ("[M4F] This shouldnt be banned", ["[cuck", "cei"], None, False),
    ("[F4M] This should also be banned [cuck]", ["[m4", "[cuck"], None, True),
    ("[F4F] This should be banned", ["[m4", "[cuck"], [("[f4f]", "4m]")], True),
    ("[F4F][F4M] This shouldnt be banned", ["[m4", "[cuck"], [("[f4f]", "4m]")], False)
])
def test_banned_tags(title, keywordlist, tag1_but_not_2, expected):
    result = title_has_banned_tag(title, keywordlist, tag1_but_not_2)
    assert result is expected


def test_banned_tags_deactivated():
    config.config['Settings']['check_banned_tags'] = 'False'
    assert title_has_banned_tag(
            "[M4F] This should be banned", ["[m4", "[cuck"], None) is False
    assert title_has_banned_tag(
            "[F4F] This should be banned", ["[m4", "[cuck"], [("[f4f]", "4m]")]) is False

    config.config['Settings']['check_banned_tags'] = 'True'
    assert title_has_banned_tag(
            "[M4F] This should be banned", ["[m4", "[cuck"], None) is True
    assert title_has_banned_tag(
            "[F4F] This should be banned", ["[m4", "[cuck"], [("[f4f]", "4m]")]) is True


@pytest.mark.sgasm
def test_soundgasm_user_extractor(monkeypatch):
    # make sure extractor also accepts init_from even if it doesnt support
    # intializing from it
    ex = SoundgasmUserExtractor("https://soundgasm.net/u/DDCherryB", init_from=None)
    # otherwise _extract_user will extract all files from the ONLINE website
    monkeypatch.setattr('gwaripper.extractors.soundgasm.SoundgasmExtractor._extract',
                        lambda x: (FileInfo(x.__class__, True, None, x.url,
                                            None, None, None, None, None),
                                   ExtractorReport(x.url, ExtractorErrorCode.NO_ERRORS)))
    fcol, report = ex._extract()

    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert report.url == "https://soundgasm.net/u/DDCherryB"
    assert sgasm_usr_audio_urls == (
            [rep.url for rep in report.children][-len(sgasm_usr_audio_urls):])

    # sgasm_usr_audio_urls should be last urls on user page
    assert sgasm_usr_audio_urls == [c.page_url for c in fcol._children][-len(sgasm_usr_audio_urls):]


@pytest.mark.sgasm
def test_extractor_soundgasm():
    # user tested above already
    url = ("https://soundgasm.net/u/kinkyshibby/F4M-Queen-of-the-Black-"
           "Coast-Pirate-Queen-Barbarian-Warrior-Seduction-Erotic-Dance-Sultry-Seriously-"
           "Extremely-Sultry-Exhibitionism-Mild-Fdom-Creampie-Script-Fill")

    # make sure extractor also accepts init_from even if it doesnt support
    # intializing from it
    ex = SoundgasmExtractor(url, init_from=None)
    assert ex.author == "kinkyshibby"
    fi, report = ex._extract()

    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert report.url == url
    assert not report.children

    assert fi.extractor is SoundgasmExtractor
    assert fi.is_audio is True
    assert fi.ext == 'm4a'
    assert fi.page_url == url
    assert fi.direct_url == ('https://media.soundgasm.net/sounds/'
                             '55b443ec89a5786815fb0fe318e01b5d8590500d.m4a')
    assert fi.id is None
    assert fi.title == ('[F4M] Queen of the Black Coast [Pirate Queen] [Barbarian Warrior] '
                        '[Seduction] [Erotic Dance] [Sultry] [Seriously, Extremely Sultry] '
                        '[Exhibitionism] [Mild Fdom] [Creampie] [Script Fill]')
    assert fi.descr == """\"Do you hear the waves? The creaking of my ship? Do you hear the aroused sighs of my crew, watching us? Do you feel how wet my soft, tight cunt is still, wrapped tight around your cock, mmm, a hot wet sheath for your blade? Oh, my king."


Script By u/Ravishagirl

Sound effects from freesound.org

freesound
Metal sword fall - GET_Accel https://freesound.org/people/GET_Accel/sounds/427255/
Waves at Baltic Sea shore.wav- pulswelle https://freesound.org/people/pulswelle/sounds/339517/
LargeWoodenShip.mp3- PimFeijen - https://freesound.org/people/PimFeijen/sounds/195193/
SwordBattle2.wav - freefire66 - https://freesound.org/people/freefire66/sounds/175951/
Sword Fight 1.MP3 - FunWithSound - https://freesound.org/people/FunWithSound/sounds/361483/"""
    assert fi.author == 'kinkyshibby'
    assert fi.parent is None
    assert fi.reddit_info is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED


@pytest.mark.sgasm
def test_extractor_soundgasm_banned_tag(monkeypatch):
    #
    # banned keyword in title
    #
    def patched_banned_tag(title, keywordlist=['f4tf'], t12=[]):
        return title_has_banned_tag(title, keywordlist, t12)

    # patch imported name in reddit module instead of definition in base module
    monkeypatch.setattr('gwaripper.extractors.soundgasm.title_has_banned_tag', patched_banned_tag)
    url = "https://soundgasm.net/u/skitty/Kidnapped-by-Your-Jealous-Little-Roommate-F4TF"

    ex = SoundgasmExtractor(url, init_from=None)
    assert ex.author == "skitty"
    fi, report = ex._extract()
    assert fi is None
    assert report.url == url
    assert report.err_code == ExtractorErrorCode.BANNED_TAG
    assert not report.children


def test_extractor_eraudica():
    url1 = "https://www.eraudica.com/e/eve/2018/Sweeter-Nothings-Sexy-Time"
    url2 = "https://www.eraudica.com/e/eve/2018/Sweeter-Nothings-Sexy-Time/gwa"

    # make sure extractor also accepts init_from even if it doesnt support
    # intializing from it
    ex = EraudicaExtractor(url1, init_from=None)
    assert ex.url == url1
    fi, report = ex._extract()

    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert report.url == url1
    assert not report.children

    assert fi.extractor is EraudicaExtractor
    assert fi.is_audio is True
    assert fi.ext == 'mp3'
    assert fi.page_url == url1
    assert fi.direct_url == ('https://data1.eraudica.com/fd/aeaf78cd-7352-4691-'
                             'af20-ea3b02237391_/Sweeter%20Nothings_Sexy%20Times.mp3')
    assert fi.id is None
    assert fi.title == 'Sweeter Nothings: Sexy Time'
    assert fi.descr == (
            "Recently someone suggested they'd like to hear a Sweet Nothings type audio "
            "that does include sex - usually SN audios are cuddly, affectionate, loving "
            "and cozy but there's no hanky panky going on. \n\nI liked the idea of trying"
            " to mix the two, to see how it might play out. \n\nI imagine this as a kind "
            "of friends-to-lovers type thing, but in a much more casual way than usual."
            " I think of it as two stressed out friends/roommates/etc who need each "
            "other tonight, but whose easy friendship, laughter and fun comes through "
            "even when they're making love for the first time. \n\nWhere will it lead?"
            " Who knows. For right now, just cuddle up and enjoy some sweeter "
            "nothings...\n\nJust a heads up - there's quite a long afterglow with this"
            " audio, and quite a long buildup. And I won't lie, in some places it's"
            " really quite silly.")
    assert fi.author == 'Eves-garden'
    assert fi.parent is None
    assert fi.reddit_info is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED

    ex = EraudicaExtractor(url2)
    # should alway be without /gwa postfix!
    assert ex.url == url1


def test_extractor_chirbit():
    url = "https://chirb.it/F5hInh"

    # make sure extractor also accepts init_from even if it doesnt support
    # intializing from it
    ex = ChirbitExtractor(url, init_from=None)
    assert ex.url == url
    fi, report = ex._extract()

    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert report.url == url
    assert not report.children

    assert fi.extractor is ChirbitExtractor
    assert fi.is_audio is True
    assert fi.ext == 'mp3'
    assert fi.page_url == url

    assert fi.direct_url.startswith(
            "https://s3.amazonaws.com/audio.chirbit.com/skitty_1543876408.mp3")
    assert "X-Amz-Credential=AKIAIHJD7T6NGQMM2VCA" in fi.direct_url

    assert fi.id == "F5hInh"
    assert fi.title == "Lonely Kitty"
    assert fi.descr is None
    assert fi.author == 'skitty'
    assert fi.parent is None
    assert fi.reddit_info is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED


def test_extractor_chirbit_banned_tag(monkeypatch):
    #
    # banned keyword in title
    #
    def patched_banned_tag(title, keywordlist=['mommy'], t12=[]):
        return title_has_banned_tag(title, keywordlist, t12)

    # patch imported name in reddit module instead of definition in base module
    monkeypatch.setattr('gwaripper.extractors.chirbit.title_has_banned_tag', patched_banned_tag)
    url = "https://chirb.it/vcP8ah"
    ex = ChirbitExtractor(url, init_from=None)
    assert ex.url == url
    fi, report = ex._extract()
    assert fi is None

    assert report.err_code == ExtractorErrorCode.BANNED_TAG
    assert report.url == url
    assert not report.children


def test_extractor_imgur_image():
    url = 'https://i.imgur.com/c0T9oSy.mp4'  # mp4

    # make sure extractor also accepts init_from even if it doesnt support
    # intializing from it
    ex = ImgurImageExtractor(url, init_from=None)
    assert ex.direct_url == url
    assert ex.url == "https://imgur.com/c0T9oSy"
    assert ex.ext == 'mp4'
    assert ex.is_direct is True
    assert ex.image_hash == "c0T9oSy"
    fi, report = ex._extract()

    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert report.url == "https://imgur.com/c0T9oSy"
    assert not report.children

    assert fi.extractor is ImgurImageExtractor
    assert fi.is_audio is False
    assert fi.ext == 'mp4'
    assert fi.page_url == "https://imgur.com/c0T9oSy"
    assert fi.direct_url == url
    assert fi.id == "c0T9oSy"
    # currently using hash as title
    assert fi.title == "c0T9oSy"
    assert fi.descr is None
    assert fi.author is None
    assert fi.parent is None
    assert fi.reddit_info is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED

    # url = 'https://i.imgur.com/gBDbyOY.png'  # png
    url = 'https://imgur.com/Ded3OiN'  # marked as mature

    ex = ImgurImageExtractor(url)
    assert ex.url == url
    assert ex.ext is None
    assert ex.is_direct is False
    assert ex.image_hash == "Ded3OiN"
    fi, report = ex._extract()

    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert report.url == url
    assert not report.children

    assert fi.extractor is ImgurImageExtractor
    assert fi.is_audio is False
    assert fi.ext == 'jpg'
    assert fi.page_url == url
    assert fi.direct_url == "https://i.imgur.com/Ded3OiN.jpg"
    assert fi.id == "Ded3OiN"
    assert fi.title == "Ded3OiN"
    assert fi.descr is None
    assert fi.author is None
    assert fi.parent is None
    assert fi.reddit_info is None
    assert fi.downloaded is DownloadErrorCode.NOT_DOWNLOADED


def test_extractor_imgur_album(monkeypatch):
    url = 'https://imgur.com/a/OPqcLpw'  # 3 jpg images

    # make sure extractor also accepts init_from even if it doesnt support
    # intializing from it
    ex = ImgurAlbumExtractor(url, init_from=None)
    ex.album_hash = "OPqcLpw"
    fcol, report = ex._extract()
    ex.image_count = 3
    ex.title = "Testing album"

    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert report.url == url
    assert len(report.children) == 3

    assert fcol.url == url
    assert fcol.id == "OPqcLpw"
    assert fcol.title == "Testing album"

    # NOTE: only check that we get the correct urls/hashes for the images
    # in the ablum the rest is already being tested by test_extractor_imgur_image
    monkeypatch.setattr('gwaripper.extractors.imgur.ImgurImageExtractor._extract',
                        lambda x: (FileInfo(x.__class__, None, None, x.url,
                                            x.direct_url, None, None, None, None),
                                   ExtractorReport(x.url, ExtractorErrorCode.NO_ERRORS)))

    img_urls = (
        ('https://imgur.com/hnDOLrH', 'https://i.imgur.com/hnDOLrH.jpg'),
        ('https://imgur.com/G52dEpB', 'https://i.imgur.com/G52dEpB.jpg'),
        ('https://imgur.com/ozozXyN', 'https://i.imgur.com/ozozXyN.jpg')
    )
    for i, img in enumerate(fcol._children):
        assert img.parent is fcol
        assert img.page_url == img_urls[i][0]
        assert img.direct_url == img_urls[i][1]

    for i, rep in enumerate(report.children):
        assert rep.err_code == ExtractorErrorCode.NO_ERRORS
        assert rep.url == img_urls[i][0]
        assert not rep.children

    # NOTE: currently always getting mp4 for all animated sources
    url = 'https://imgur.com/a/tcl9AuW'  # gif, webm+sound, mp4

    ex = ImgurAlbumExtractor(url)
    ex.album_hash = "tcl9AuW"
    fcol, report = ex._extract()
    ex.image_count = 3
    ex.title = "Test album animated ?"

    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert report.url == url
    assert len(report.children) == 3

    assert fcol.url == url
    assert fcol.id == "tcl9AuW"
    assert fcol.title == "Test album animated ?"

    # NOTE: extract() already patched
    animated_urls = (
        # orig is gif but we always get the mp4
        ('https://imgur.com/v5SfiSJ', 'https://i.imgur.com/v5SfiSJ.mp4'),
        ('https://imgur.com/YgPICmf', 'https://i.imgur.com/YgPICmf.mp4'),
        ('https://imgur.com/NLm5ffm', 'https://i.imgur.com/NLm5ffm.mp4')
    )
    for i, img in enumerate(fcol._children):
        assert img.parent is fcol
        assert img.page_url == animated_urls[i][0]
        assert img.direct_url == animated_urls[i][1]

    for i, rep in enumerate(report.children):
        assert rep.err_code == ExtractorErrorCode.NO_ERRORS
        assert rep.url == animated_urls[i][0]
        assert not rep.children


reddit_extractor_url_expected = [
        ("https://old.reddit.com/r/gonewildaudio/comments/6dvum7/"
         "f4m_my_daughter_is_an_idiot_for_breaking_up_with/",  # one sgasm link in selftext
         ["https://soundgasm.net/u/sassmastah77/F4M-My-Daughter-is-an-Idiot-for-"
          "Breaking-Up-With-You-Let-Me-Help-You-Feel-Better"],
         {
             # fcol
             "url": ('https://www.reddit.com/r/gonewildaudio/comments/6dvum7/'
                     'f4m_my_daughter_is_an_idiot_for_breaking_up_with/'),
             "id": '6dvum7',
             "title": ("[F4M] My Daughter is an Idiot for Breaking Up With You... "
                       "Let Me Help You Feel Better [milf] [sex with your ex's sweet "
                       "+ sexy mom] [realistic slow build] [kissing] [sloppy wet "
                       "handjob + deep-throating blowjob] [dirty talk] [sucking my big "
                       "tits] [riding you on the couch] [creampie] [improv]"),
             "author": "sassmastah77",
             # ri
             "permalink": ("/r/gonewildaudio/comments/6dvum7/f4m_my_daughter_is_an_"
                           "idiot_for_breaking_up_with/"),
             "selftext": """**It\'s the fantasy you never knew you had!**\n\n&nbsp;\n\nGetting dumped is awful. But I bet it wouldn\'t be quiiiiite as painful if her mom took it upon herself to comfort you... with her body. \n_____________________________________________________________________________\n\n\n*"Wow I can\'t believe my daughter just broke up with you! You\'re so cute and sweet and you\'ve been such a good boyfriend to her... I - I, um, I made you some cookies. Come sit with me while we wait for them to cool off, k?"*\n___________________________________________________________________________________\n\n\n***[CLICK HERE FOR AUDIO!](https://soundgasm.net/u/sassmastah77/F4M-My-Daughter-is-an-Idiot-for-Breaking-Up-With-You-Let-Me-Help-You-Feel-Better)***\n\n&nbsp;\n\nPlease note that this audio uses some realistic home environment soundfx for immersion (so don\'t be jolted by the cell phone ringing or doorbell sounds!)\n\n_____________________________________________________________________________\n*I\'m still super behind in responding to stuff :( ... I hope that won\'t keep you from letting me know if you enjoyed this! Your comments and PMs are the reason I keep posting!! And you can also click [here](https://redd.it/50cng2) to check out a full listing of all my audios! <3*""",
             "created_utc": 1496001999.0,
             "subreddit": "gonewildaudio",
             "r_post_url": ("https://www.reddit.com/r/gonewildaudio/comments/6dvum7/"
                            "f4m_my_daughter_is_an_idiot_for_breaking_up_with/"),
         }),

        ("https://www.reddit.com/r/gonewildaudio/comments/e2kcq5/"
         "f4m_getting_high_with_your_hot_tomboy_friend/",  # sgasm link in url
         ["https://soundgasm.net/u/miss_pretty_please/Getting-high-with-your-hot-tomboy-friend"],
         {
             # fcol
             "url": ('https://www.reddit.com/r/gonewildaudio/comments/e2kcq5/'
                     'f4m_getting_high_with_your_hot_tomboy_friend/'),
             "id": 'e2kcq5',
             "title": ("[F4M] Getting High with Your Hot Tomboy Friend [friends to lovers]"
                       "[smoke buddies][rambling][smoking a blunt][tomboy turns into a "
                       "needy little slut][grinding][sloppy blow job][69][riding you]"
                       "[bed noises][cum with me][creampie]"),
             "author": "miss_pretty_please",
             # ri
             "permalink": ("/r/gonewildaudio/comments/e2kcq5/f4m_getting_high_"
                           "with_your_hot_tomboy_friend/"),
             "selftext": None,
             "created_utc": 1574879455.0,
             "subreddit": "gonewildaudio",
             "r_post_url": ("https://soundgasm.net/u/miss_pretty_please/Getting"
                            "-high-with-your-hot-tomboy-friend")
         }),
        ("https://www.reddit.com/r/gonewildaudio/comments/3gs9dm/"
         "f4m_nurse_eve_time_for_your_physical/",  # eraudica in url
         # normally /gwa would be stripped but since we use the DummyExtractor it won't
         # but we only care that the url WAS found
         ["http://eraudica.com/e/eve/2015/Nurse-Eve-Time-For-Your-Physical/gwa"],
         {
             # fcol
             "url": ('https://www.reddit.com/r/gonewildaudio/comments/3gs9dm/'
                     'f4m_nurse_eve_time_for_your_physical/'),
             "id": '3gs9dm',
             "title": ("[F4M] Nurse Eve: Time for your physical [medical][handjob]"
                       "[cocksucking][fucking][what a specimen!][post with photos]"),
             "author": "Eves-garden",
             # ri
             "permalink": "/r/gonewildaudio/comments/3gs9dm/f4m_nurse_eve_time_for_your_physical/",
             "selftext": None,
             "created_utc": 1439422018.0,
             "subreddit": "gonewildaudio",
             "r_post_url": ("http://eraudica.com/e/eve/2015/Nurse-Eve-Time-For-Your-Physical/gwa"),
         }),
        ("https://www.reddit.com/r/gonewildaudio/comments/4r33ek/"
         "f4m_a_lesbian_does_her_male_friend_a_favor_script/",  # banned keyword
         [], None),
        ("https://www.reddit.com/r/gonewildaudio/comments/69evvm/"
         "f4mcougarstrangers_a_new_neighbor_moves_in_next/",  # non supported link (literotica)
         "non-supported", None),
        # i.redd.it in selftext
        # https://old.reddit.com/r/gonewildaudio/comments/izmq8r/fff4m_three_elven_princesses_come_together_to/
        ("https://www.reddit.com/r/gonewildaudio/comments/8pyayj/"
         "ff4m_busting_beauty_joip_teacherslubegigglingtit/",
         # 1 sg link in text + imgur album
         ["https://soundgasm.net/u/sweetcarolinekisses/JOIP-to-Busty-Babes",
          "https://imgur.com/a/lb8rc1t"],
         {
             # fcol
             "url": ("https://www.reddit.com/r/gonewildaudio/comments/8pyayj/"
                     "ff4m_busting_beauty_joip_teacherslubegigglingtit/"),
             "id": '8pyayj',
             "title": ("[FF4M] Busting Beauty JOIP [teachers][lube][giggling]"
                       "[tit fucking][interactive][marathon][gallery][explicit][cock worship]"),
             "author": "sweetcarolinekisses",
             # ri
             "permalink": ("/r/gonewildaudio/comments/8pyayj/"
                           "ff4m_busting_beauty_joip_teacherslubegigglingtit/"),
             "selftext": """JOIP time again! This time I was joined by u/brainy_babe as a fellow teacher. We help you learn about your gorgeous cock.\n\n[Here](https://imgur.com/a/lb8rc1t) is an album for you to follow along with. \n\n[Here](https://soundgasm.net/u/sweetcarolinekisses/JOIP-to-Busty-Babes) is the audio to listen to while we look at the girls with you and direct how you jerk off. \n\nAll the thanks to BrainyBabe for playing with me and to u/VincentPrince5 for making the album!\n\n\n""",
             "created_utc": 1528602283.0,
             "subreddit": "gonewildaudio",
             "r_post_url": ("https://www.reddit.com/r/gonewildaudio/comments/8pyayj/"
                            "ff4m_busting_beauty_joip_teacherslubegigglingtit/"),
         }),
         ("https://www.reddit.com/r/pillowtalkaudio/comments/feagis/f4m_seven_minutes"
          "_in_heaven_with_your_crush/",  # xpost with one sgasm link in text
          # xposted url: https://www.reddit.com/r/VanillaAudio/comments/feafko/f4m_seven_minutes_in_heaven_with_your_crush/
          ["https://soundgasm.net/u/Katealexis/F4M-Seven-minutes-in-heaven-with-your-crush-"
           "College-party-sweet-to-seductive-confession-friends-to-lovers-french-kissing-"
           "making-out-hand-holding-romantic-cute-sweet-giggles"],
          {
              # fcol
              "url": ("https://www.reddit.com/r/VanillaAudio/comments/feafko/"
                      "f4m_seven_minutes_in_heaven_with_your_crush/"),
              "id": 'feafko',
              "title": ("[F4M] Seven minutes in heaven with your crush [College party] "
                        "[sweet to seductive] [confession] [friends to lovers] [English "
                        "accent] [french kissing] [making out] [hand holding] [romantic] "
                        "[cute] [sweet] [giggles]"),
              "author": "TheGoddessKate",
              # ri
              "permalink": ("/r/VanillaAudio/comments/feafko/f4m_seven_minutes"
                            "_in_heaven_with_your_crush/"),
              "selftext": """Hey you,\n\nI'm so glad to see you, we always have such fun when we chat and it's been too long! Are you enjoying the party?\n\nOh wow, it looks like we've been nominated for 7 minutes in heaven, everyone's cheering! Well I'm game if you are. As a matter of fact there's something I've been meaning to tell you..\n\nHow about you [take me into the closet](https://soundgasm.net/u/Katealexis/F4M-Seven-minutes-in-heaven-with-your-crush-College-party-sweet-to-seductive-confession-friends-to-lovers-french-kissing-making-out-hand-holding-romantic-cute-sweet-giggles)\n\n\\_\\_\\_\\_\\_\n\nThis wonderfully sweet and sexy script is by u/OratioFidelis and as soon as I read it I knew I'd enjoy making it as my first submission to Vanilla Audio😊\n\nI'm Kate from England and I'm brand new to the world of reddit audios (wow, who knew this existed - mind blown!), though not to all things erotica. I've been a naughty & fetish content creator for nearly 9 years now and I'm excited to discover you all and get to know you!\n\n\\_\\_\\_\\_\\_\n\nI'd love to hear if I gave you the tingles, or left you wanting more in a comment or pm over on my sub r/goddesskatealexis or my anonymous [feedback form](https://forms.gle/cGSrUbJ7p775Ey2V8) 😉. I get a lot of mail though and can't chat as much as I would wish, so just know I love you all and appreciate your feedback❤️""",
              "created_utc": 1583482224.0,
              "subreddit": "VanillaAudio",
              "r_post_url": ("https://www.reddit.com/r/VanillaAudio/comments/feafko/"
                             "f4m_seven_minutes_in_heaven_with_your_crush/"),
          }),
    ]


class DummyExtractor(BaseExtractor):
    EXTRACTOR_NAME = "Dummy"
    BASE_URL = "dummy.org"

    supported = [ex for ex in AVAILABLE_EXTRACTORS if ex is not RedditExtractor]

    def __init__(self, url, init_from=None):
        self.url = url
        self.init_from = init_from
        self.is_audio = False

    # only match supported urls
    @classmethod
    def is_compatible(cls, url):
        # to filter out skittykat.cc/exclusive links
        if "skitty" in url and "/exclusive/" in url:
            return False
        return any(ex.is_compatible(url) for ex in cls.supported)

    @property
    def page_url(self):
        return self.url

    def _extract(self):
        return (FileInfo(self.__class__, True, None, self.url,
                         None, None, None, None, None),
                ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS))


def test_extractor_reddit(setup_tmpdir, monkeypatch, caplog):
    # NOTE: use DummyExtractor since we only care about the extracted urls
    # but make sure to still return RedditExtractor since that is used
    # to avoid extracting forther reddit submissions
    backup_find = find_extractor  # save orig func
    mock_findex = lambda x: (RedditExtractor if RedditExtractor.is_compatible(x)
                             else DummyExtractor if DummyExtractor.is_compatible(x) else
                             None)
    monkeypatch.setattr('gwaripper.extractors.find_extractor', mock_findex)

    # NOTE: IMPORTANT setup banned keywords and tag1_but_not_2
    # just assigning a new value will not work if any other module imports
    # them as "from config import .." then the KEYWORDLIST etc.
    # will be a symbol in the importing module that holds a ref to KEYWORDLIST
    # _assigning_ config.KEYWORDLIST from another module will not change KEYWORDLIST
    # in the other module since it's its own symbol that still holds a ref to the
    # original value at the time of import
    # -> import as config.KEYWORDLIST etc. in that module or use methods on mutable
    # types to change them e.g. list.clear(); list.append()
    # using import config everywhere so we can do:
    config.KEYWORDLIST = ['request']
    config.TAG1_BUT_NOT_TAG2 = [("[script offer]", "[script fill]")]

    #
    # no response from reddit
    #
    class DummyResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    def patched_post(*args, **kwargs):
        raise prawcore.exceptions.ResponseException(DummyResponse(503))

    bu_post = prawcore.auth.BaseAuthenticator._post
    monkeypatch.setattr('prawcore.auth.BaseAuthenticator._post', patched_post)
    ex = RedditExtractor(reddit_extractor_url_expected[0][0])

    caplog.clear()
    ri, report = ex._extract()

    assert ri is None
    assert report.url == reddit_extractor_url_expected[0][0]
    assert report.err_code == ExtractorErrorCode.NO_RESPONSE
    assert len(report.children) == 0

    # err on client side
    def patched_post(*args, **kwargs):
        raise prawcore.exceptions.ResponseException(DummyResponse(403))

    monkeypatch.setattr('prawcore.auth.BaseAuthenticator._post', patched_post)

    ex = RedditExtractor(reddit_extractor_url_expected[0][0])

    caplog.clear()
    with pytest.raises(InfoExtractingError) as err:
        ri, report = ex._extract()
    assert err.value.msg.startswith("The Reddit API returned an HTTP status code")

    # reset
    monkeypatch.setattr('prawcore.auth.BaseAuthenticator._post', bu_post)

    #
    #
    #

    caplog.set_level(logging.INFO)
    for url, found_urls, attr_val_dict in reddit_extractor_url_expected:
        # important that actual extractors are tested since
        # we apparently expect RedditInfo to be None which is the case
        # for banned keywords or not finding supported AUDIO urls
        if attr_val_dict is None:
            monkeypatch.setattr('gwaripper.extractors.find_extractor', backup_find)

        # make sure extractor also accepts init_from even if it doesnt support
        # intializing from it
        ex = RedditExtractor(url, init_from=None)

        caplog.clear()
        ri, report = ex._extract()

        if attr_val_dict is not None:
            assert report.url == url
            assert report.err_code == ExtractorErrorCode.NO_ERRORS
            # print("\n".join(rep.url for rep in report.children))
            assert len(report.children) == len(found_urls)

            for attr_name, value in attr_val_dict.items():
                assert getattr(ri, attr_name) == value

            # IMPORTANT check that parent and reddit_info was set
            for child in ri._children:
                assert child.parent is ri

            sorted_urls = list(sorted(found_urls))
            for i, rep in enumerate(sorted(report.children, key=lambda x: x.url)):
                assert rep.url == sorted_urls[i]
                assert rep.err_code == ExtractorErrorCode.NO_ERRORS
                assert not rep.children
        elif type(found_urls) is str:
            # no supported link
            assert ri is None

            assert report.url == url
            assert report.err_code == ExtractorErrorCode.ERROR_IN_CHILDREN
            assert len(report.children) == 1
            assert report.children[0].err_code == ExtractorErrorCode.NO_EXTRACTOR
            assert report.children[0].url == "https://www.literotica.com/s/cougar-tales-new-neighbor"
            assert not report.children[0].children

            assert ("Outgoing submission URL is not supported: "
                    "https://www.literotica.com/s/cougar-tales-new-neighbor") in caplog.text
        else:
            msg = caplog.records[0].message
            assert msg.startswith("Banned keyword: no '[script fill]' in title "
                                  "where '[script offer]' is in")
            assert ri is None
            assert report.url == url
            assert report.err_code == ExtractorErrorCode.BANNED_TAG
            assert not report.children

        # restore patched version for other tests
        if attr_val_dict is None:
            monkeypatch.setattr('gwaripper.extractors.find_extractor', mock_findex)

    #
    # test using a praw submission instead of url
    #
    r = reddit_praw()
    sub = r.submission(id=reddit_extractor_url_expected[0][2]['id'])

    # pass in old.reddit.com... url and submission object
    ex = RedditExtractor(reddit_extractor_url_expected[0][0], init_from=sub)

    caplog.clear()
    ri, report = ex._extract()

    assert report.url == reddit_extractor_url_expected[0][0]
    assert report.err_code == ExtractorErrorCode.NO_ERRORS
    assert len(report.children) == 1  # static otherwise we need to change below

    for attr_name, value in reddit_extractor_url_expected[0][2].items():
        assert getattr(ri, attr_name) == value

    # IMPORTANT check that parent and reddit_info was set
    for child in ri._children:
        assert child.parent is ri
    # only 1 child
    rep = report.children[0]
    assert rep.url == reddit_extractor_url_expected[0][1][0]
    assert rep.err_code == ExtractorErrorCode.NO_ERRORS
    assert not rep.children


def test_extractor_reddit_banned_tag_linktext(monkeypatch, caplog):
    #
    # one banned keyword in linktext
    #
    bu_banned_tag = title_has_banned_tag

    def patched_banned_tag(title, keywordlist=[], t12=[]):
        return bu_banned_tag(title, keywordlist, [('4f', '4m')])

    # patch imported name in reddit module instead of definition in base module
    monkeypatch.setattr('gwaripper.extractors.reddit.title_has_banned_tag', patched_banned_tag)
    url = ("https://www.reddit.com/r/gonewildaudio/comments/h85o4x/f4m_and_f4f_tomboy"
           "_friend_helps_you_save_money_on/")
    ex = RedditExtractor(url)

    caplog.clear()
    ri, report = ex._extract()
    assert ri.author == 'AuralCandy'
    assert ri.id == 'h85o4x'
    assert "Banned keyword: no '4m' in title where '4f' is in: 4f link here" in caplog.text

    assert report.url == url
    assert report.err_code == ExtractorErrorCode.ERROR_IN_CHILDREN
    assert len(report.children) == 3

    assert report.children[0].url == (
            "https://www.reddit.com/r/gonewildaudio/comments/53fi5m/f4m_script_offer_"
            "tomboy_saves_her_best_friend/?utm_source=share&utm_medium=ios_app&utm_name=iossmf")
    assert report.children[0].err_code == ExtractorErrorCode.STOP_RECURSION
    assert report.children[1].url == (
            "https://soundgasm.net/u/auralcandy/Tomboy-Friend-Helps"
            "-You-Save-Money-on-Strippers-4M")
    assert report.children[1].err_code == ExtractorErrorCode.NO_ERRORS
    assert report.children[2].url == (
            "https://soundgasm.net/u/auralcandy/Tomboy-Friend-Helps"
            "-You-Save-Money-on-Strippers-4F")
    assert report.children[2].err_code == ExtractorErrorCode.BANNED_TAG


class DummyFileInfo(FileInfo):
    def __init__(self):
        super().__init__(object, True, 'ext', 'url', 'fileURL', None, 'title'
                         'descr', 'author', None, None)


class DummyFileCol(FileCollection):
    def __init__(self):
        super().__init__(object, '', None, None, 'author', children=[])


def test_base_extract(monkeypatch, caplog):
    exerr = ExtractorErrorCode
    caplog.set_level(logging.WARNING)

    #
    # extractor class has is_broken set -> url should be skipped
    #
    BaseExtractor.is_broken = True
    res, rep = BaseExtractor.extract('url')
    assert res is None
    assert rep.err_code == ExtractorErrorCode.BROKEN_EXTRACTOR
    assert caplog.records[0].message == "Skipping URL 'url' due to broken extractor: Base"

    caplog.clear()
    # should not append to parent
    parent = DummyFileCol()
    # should change err_code to ERROR_IN_CHILDREN
    parent_report = ExtractorReport('url', exerr.NO_ERRORS)
    res, rep = BaseExtractor.extract('url', parent=parent, parent_report=parent_report)
    assert res is None
    assert rep.err_code == exerr.BROKEN_EXTRACTOR
    # report appended to parent_report
    assert parent_report.children[0] is rep
    assert len(parent_report.children) == 1
    # err set on parent_report
    assert parent_report.err_code == exerr.ERROR_IN_CHILDREN
    # parent not modified
    assert not parent._children
    assert caplog.records[0].message == "Skipping URL 'url' due to broken extractor: Base"

    # reset
    BaseExtractor.is_broken = False

    #
    # check that init_from correctly passed
    #
    # patch so we can inspect the extractor afterwards
    monkeypatch.setattr(
        "test_extractors.DummyExtractor._extract", lambda x: (x, ExtractorReport('a', exerr.NO_ERRORS)))
    extr, _ = DummyExtractor.extract('url1234', init_from='foo34bar82')
    assert extr.url == 'url1234'
    assert extr.init_from == 'foo34bar82'

    #
    # successful with and without parent
    #
    dfi = DummyFileInfo()
    drep = ExtractorReport('url354', exerr.NO_ERRORS)

    monkeypatch.setattr("gwaripper.extractors.base.BaseExtractor._extract",
                        lambda x: (dfi, drep))

    res, rep = BaseExtractor.extract('url354')
    assert res is dfi
    assert res.parent is None
    # set ref to report on info
    assert res.report is rep

    assert rep.url == 'url354'
    assert rep.err_code == exerr.NO_ERRORS
    assert not rep.children

    # with parent and parent_report
    dfi = DummyFileInfo()
    drep = ExtractorReport('url354', exerr.NO_ERRORS)
    parent = DummyFileCol()
    parent_report = ExtractorReport('parurl354', exerr.NO_ERRORS)
    res, rep = BaseExtractor.extract('url354', parent=parent, parent_report=parent_report)
    assert res is dfi
    assert res.report is rep
    # parent set and appendend
    assert res.parent is parent
    assert parent._children[0] is res

    assert rep.url == 'url354'
    assert rep.err_code == exerr.NO_ERRORS
    assert not rep.children

    # report appended to parent_report
    assert parent_report.children[0] is rep
    assert len(parent_report.children) == 1
    # err unchangend on parent_report
    assert parent_report.err_code == exerr.NO_ERRORS

    #
    # successful _extract return fcol
    #
    dfi = DummyFileCol()
    drep = ExtractorReport('urlcol354', exerr.NO_ERRORS)

    res, rep = BaseExtractor.extract('urlcol354')
    assert res is dfi
    assert res.parent is None
    # set ref to report on info
    assert res.report is rep

    assert rep.url == 'urlcol354'
    assert rep.err_code == exerr.NO_ERRORS
    assert not rep.children

    #
    # child with error only modifies parent_report err if it still was at NO_ERRORS
    #
    dfi = DummyFileInfo()
    drep = ExtractorReport('url3542', exerr.NO_RESPONSE)  # err on child
    parent = DummyFileCol()
    parent_report = ExtractorReport('parurl3542', exerr.NO_ERRORS)  # no err so far
    res, rep = BaseExtractor.extract('url3542', parent=parent, parent_report=parent_report)
    assert res is dfi
    assert res.report is rep
    # parent set and appendend
    assert res.parent is parent
    assert parent._children[0] is res

    assert rep.url == 'url3542'
    assert rep.err_code == exerr.NO_RESPONSE
    assert not rep.children

    # report appended to parent_report
    assert parent_report.children[0] is rep
    assert len(parent_report.children) == 1
    # err set on parent_report
    assert parent_report.err_code == exerr.ERROR_IN_CHILDREN

    # ----- parent already has different error ----
    dfi = DummyFileInfo()
    drep = ExtractorReport('url35426', exerr.NO_EXTRACTOR)  # err on child
    parent = DummyFileCol()
    parent_report = ExtractorReport('parurl35426', exerr.NO_SUPPORTED_AUDIO_LINK)  # has err
    res, rep = BaseExtractor.extract('url35426', parent=parent, parent_report=parent_report)
    assert res is dfi
    assert res.report is rep
    # parent set and appendend
    assert res.parent is parent
    assert parent._children[0] is res

    assert rep.url == 'url35426'
    assert rep.err_code == exerr.NO_EXTRACTOR
    assert not rep.children

    # report appended to parent_report
    assert parent_report.children[0] is rep
    assert len(parent_report.children) == 1
    # err set on parent_report
    assert parent_report.err_code == exerr.NO_SUPPORTED_AUDIO_LINK

    #
    # extr returning broken err code without raising not is_broken set
    #
    dfi = None
    drep = ExtractorReport('url354267', exerr.BROKEN_EXTRACTOR)
    parent = DummyFileCol()
    parent_report = ExtractorReport('parurl354267', exerr.NO_SUPPORTED_AUDIO_LINK)
    res, rep = BaseExtractor.extract('url354267', parent=parent, parent_report=parent_report)
    assert res is None
    assert rep is drep
    assert rep.err_code == exerr.BROKEN_EXTRACTOR
    assert not BaseExtractor.is_broken

    #
    # extract excepts all exceptions
    # returns BROKEN_EXTRACTOR report and sets on parent_report
    #

    caplog.set_level(logging.DEBUG)
    caplog.clear()

    class DummyException(Exception):
        pass

    def raises(x):
        raise DummyException()

    monkeypatch.setattr("gwaripper.extractors.base.BaseExtractor._extract", raises)

    res, rep = BaseExtractor.extract('url354')
    assert res is None

    assert rep.url == 'url354'
    assert rep.err_code == exerr.BROKEN_EXTRACTOR
    assert not rep.children

    assert BaseExtractor.is_broken is True
    assert caplog.records[0].levelname == 'ERROR'
    assert caplog.records[0].message == (
            "Error occured while extracting information from 'url354' "
            "- site structure or API probably changed! See if there are "
            "updates available!")
    assert caplog.records[1].levelname == 'DEBUG'
    # pytest logcapture breaks when printing exc_info so message is not set here
    # assert caplog.records[1].message == "Full exception info for unexpected extraction failure:"

    BaseExtractor.is_broken = False
    # with parent and parent_report
    parent = DummyFileCol()
    parent_report = ExtractorReport('parurl354', exerr.NO_ERRORS)
    caplog.clear()
    res, rep = BaseExtractor.extract('url354', parent=parent, parent_report=parent_report)
    assert res is None
    assert not parent._children

    assert rep.url == 'url354'
    assert rep.err_code == exerr.BROKEN_EXTRACTOR
    assert not rep.children

    # report appended to parent_report
    assert parent_report.children[0] is rep
    assert len(parent_report.children) == 1
    # parent err code changed
    assert parent_report.err_code == exerr.ERROR_IN_CHILDREN

    assert caplog.records[0].levelname == 'ERROR'
    assert caplog.records[0].message == (
            "Error occured while extracting information from 'url354' "
            "- site structure or API probably changed! See if there are "
            "updates available!")

    # reset
    BaseExtractor.is_broken = False

    #
    # NoAuthenticationError
    #

    def raises(x):
        raise NoAuthenticationError('no auth')

    monkeypatch.setattr("gwaripper.extractors.base.BaseExtractor._extract", raises)

    parent = DummyFileCol()
    parent_report = ExtractorReport('parurl354', exerr.NO_SUPPORTED_AUDIO_LINK)  # has err
    caplog.clear()
    res, rep = BaseExtractor.extract('url354', parent=parent, parent_report=parent_report)
    assert res is None
    assert not parent._children

    assert BaseExtractor.is_broken is True

    assert rep.url == 'url354'
    assert rep.err_code == exerr.NO_AUTHENTICATION
    assert not rep.children

    # report appended to parent_report
    assert parent_report.children[0] is rep
    assert len(parent_report.children) == 1
    # parent err code _NOT_ changed
    assert parent_report.err_code == exerr.NO_SUPPORTED_AUDIO_LINK

    assert caplog.records[0].levelname == 'ERROR'
    assert caplog.records[0].message == (
            "NoAuthenticationError: no auth Extractor will be marked as broken so subsequent "
            "downloads of the same type will be skipped!")

    # reset
    BaseExtractor.is_broken = False

    #
    # InfoExtractingError, NoAPIResponseError, AuthenticationFailed
    #
    caplog.set_level(logging.DEBUG)

    for exc in (InfoExtractingError, NoAPIResponseError, AuthenticationFailed):
        def raises(x):
            raise exc('errtext', 'url354')

        monkeypatch.setattr("gwaripper.extractors.base.BaseExtractor._extract", raises)

        parent = DummyFileCol()
        parent_report = ExtractorReport('parurl354', exerr.NO_ERRORS)
        caplog.clear()
        res, rep = BaseExtractor.extract('url354', parent=parent, parent_report=parent_report)
        assert res is None
        assert not parent._children

        assert BaseExtractor.is_broken is True

        assert rep.url == 'url354'
        assert rep.err_code == exerr.BROKEN_EXTRACTOR
        assert not rep.children

        # report appended to parent_report
        assert parent_report.children[0] is rep
        assert len(parent_report.children) == 1
        # parent err code changed
        assert parent_report.err_code == exerr.ERROR_IN_CHILDREN

        assert caplog.records[0].levelname == 'ERROR'
        assert caplog.records[0].message == f"{exc.__name__}: errtext (URL was: url354)"
        assert caplog.records[1].levelname == 'DEBUG'
        # pytest can't caputre log msg with exc_info

        # reset
        BaseExtractor.is_broken = False


# only testing >=400
@pytest.mark.parametrize(
        'http_code, expected',
        [(404, False), (408, False), (410, False), (range(400, 404), True),
         (range(405, 408), True), (409, True), (range(411, 418), True),
         (501, True), (505, True), (500, False), (range(502, 505), False,)]
        )
def test_extr_broken_http_code(http_code, expected):
    try:
        for htc in http_code:
            assert BaseExtractor.http_code_is_extractor_broken(htc) is expected
    except TypeError:
        assert BaseExtractor.http_code_is_extractor_broken(http_code) is expected


def test_extractor_skittykat_patreon(monkeypatch):
    # NOTE: use DummyExtractor since we only care about the extracted urls
    # but make sure to still return RedditExtractor since that is used
    # to avoid extracting forther reddit submissions
    backup_find = find_extractor  # save orig func
    mock_findex = lambda x: (RedditExtractor if RedditExtractor.is_compatible(x)
                             else DummyExtractor if DummyExtractor.is_compatible(x) else
                             None)
    monkeypatch.setattr('gwaripper.extractors.find_extractor', mock_findex)

    extr = SkittykatExtractor("https://skittykat.cc/patreon/how-many-kisses-til-you-pop/")
    assert extr.content_category == 'patreon'
    assert extr.id == 'how-many-kisses-til-you-pop'

    fc, report = extr._extract()

    # TODO fix this: How Many Kisses 'Til You Pop?
    # assert fc.title == "How Many Kisses æTil You Pop?"
    assert fc.author == "skitty-gwa"

    assert len(fc.children) == 0
    assert report.err_code == ExtractorErrorCode.ERROR_IN_CHILDREN

    assert len(report.children) == 2
    assert report.children[0].err_code == ExtractorErrorCode.NO_EXTRACTOR
    # TODO fix finding this
    assert report.children[0].url == "https://skittykat.cc/exclusive/"
    assert report.children[1].err_code == ExtractorErrorCode.STOP_RECURSION
    assert report.children[1].url == "https://www.reddit.com/r/gonewildaudio/comments/bxlykc/f4m_milking_a_yummy_little_cutie_gentle_fdom/"


def test_extractor_skittykat_sg_and_reddit(monkeypatch):
    # NOTE: use DummyExtractor since we only care about the extracted urls
    # but make sure to still return RedditExtractor since that is used
    # to avoid extracting further reddit submissions
    backup_find = find_extractor  # save orig func
    mock_findex = lambda x: (RedditExtractor if RedditExtractor.is_compatible(x)
                             else DummyExtractor if DummyExtractor.is_compatible(x) else
                             None)
    monkeypatch.setattr('gwaripper.extractors.find_extractor', mock_findex)
    def reddit_extract(self):
        return None, ExtractorReport(
                "https://www.reddit.com/r/gonewildaudio/comments/jal6m0/f4mf4tf_"
                "kidnapped_by_your_jealous_little_roommate/",
                ExtractorErrorCode.NO_ERRORS)
    monkeypatch.setattr('gwaripper.extractors.reddit.RedditExtractor._extract', reddit_extract)


    extr = SkittykatExtractor("https://skittykat.cc/gonewildaudio/kidnapped-by-your-jealous-little-roommate/")
    assert extr.content_category == 'gonewildaudio'
    assert extr.id == 'kidnapped-by-your-jealous-little-roommate'

    fc, report = extr._extract()

    assert fc.title == "Kidnapped by Your Jealous Little Roommate"
    assert fc.author == "skitty-gwa"

    assert fc.children[0].page_url == "https://soundgasm.net/u/skitty/Kidnapped-by-Your-Jealous-Little-Roommate-F4M"
    assert fc.children[1].page_url == "https://soundgasm.net/u/skitty/Kidnapped-by-Your-Jealous-Little-Roommate-F4TF"

    # reddit extractor would normally also return FileInfos but it was patched above
    assert len(fc.children) == 2
    assert report.err_code == ExtractorErrorCode.NO_ERRORS

    assert len(report.children) == 6
    assert report.children[0].err_code == ExtractorErrorCode.NO_ERRORS
    assert report.children[0].url == ("https://www.reddit.com/r/gonewildaudio/comments/jal6m0/f4mf4tf_"
        "kidnapped_by_your_jealous_little_roommate/")
    assert report.children[1].err_code == ExtractorErrorCode.NO_ERRORS
    assert report.children[1].url == "https://soundgasm.net/u/skitty/Kidnapped-by-Your-Jealous-Little-Roommate-F4M"
    assert report.children[2].err_code == ExtractorErrorCode.NO_ERRORS
    assert report.children[2].url == "https://soundgasm.net/u/skitty/Kidnapped-by-Your-Jealous-Little-Roommate-F4TF"
    assert report.children[3].err_code == ExtractorErrorCode.STOP_RECURSION
    assert report.children[3].url == "https://www.reddit.com/r/yandere/comments/fw7tht/im_a_normal_person_i_swear/"
    assert report.children[4].err_code == ExtractorErrorCode.STOP_RECURSION
    assert report.children[4].url == "https://www.reddit.com/r/gonewildaudio/comments/e6nka1/f4m_yandere_halfpint_threatens_to_love_you_dark/"
    assert report.children[5].err_code == ExtractorErrorCode.STOP_RECURSION
    assert report.children[5].url == "https://www.reddit.com/r/gonewildaudio/comments/ha7cvo/f4m_script_offer_kidnapped_by_your_jealous_little/"


def test_extractor_skittykat_embed(monkeypatch):
    # NOTE: use DummyExtractor since we only care about the extracted urls
    # but make sure to still return RedditExtractor since that is used
    # to avoid extracting forther reddit submissions
    backup_find = find_extractor  # save orig func
    mock_findex = lambda x: (RedditExtractor if RedditExtractor.is_compatible(x)
                             else DummyExtractor if DummyExtractor.is_compatible(x) else
                             None)
    monkeypatch.setattr('gwaripper.extractors.find_extractor', mock_findex)


    extr = SkittykatExtractor("https://skittykat.cc/gonewildaudio/secret-playtime-mommy/")
    assert extr.content_category == 'gonewildaudio'
    assert extr.id == 'secret-playtime-mommy'

    fc, report = extr._extract()

    assert fc.title == "Secret Playtime Mommy"
    assert fc.author == "skitty-gwa"

    # reddit extractor would normally also return FileInfos but it was patched above
    assert len(fc.children) == 2
    assert report.err_code == ExtractorErrorCode.NO_ERRORS

    assert fc.children[0].title == "F4TF “Good Girl” Version"
    assert fc.children[0].page_url == "https://skittykat.cc/wp-content/uploads/2021/04/enno-secret-playtime-f4tf.mp3?_=1"
    assert fc.children[0].is_audio is True
    assert fc.children[0].ext == "mp3"
    assert fc.children[1].title == "F4M “Good Boy” Version"
    assert fc.children[1].page_url == "https://skittykat.cc/wp-content/uploads/2021/06/enno-secret-playtime-f4m.mp3?_=2"
    assert fc.children[1].is_audio is True
    assert fc.children[1].ext == "mp3"

    assert len(report.children) == 2
    assert report.children[0].err_code == ExtractorErrorCode.NO_ERRORS
    assert report.children[0].url == "https://skittykat.cc/wp-content/uploads/2021/04/enno-secret-playtime-f4tf.mp3?_=1"
    assert report.children[1].err_code == ExtractorErrorCode.NO_ERRORS
    assert report.children[1].url == "https://skittykat.cc/wp-content/uploads/2021/06/enno-secret-playtime-f4m.mp3?_=2"

SKITTY_U200B_HTML = """<div class="elementor-section-wrap">
							<section class="elementor-section elementor-top-section elementor-element elementor-element-8827f48 elementor-section-boxed elementor-section-height-default elementor-section-height-default" data-id="8827f48" data-element_type="section">
						<div class="elementor-container elementor-column-gap-default">
							<div class="elementor-row">
					<div class="elementor-column elementor-col-100 elementor-top-column elementor-element elementor-element-e041b51" data-id="e041b51" data-element_type="column">
			<div class="elementor-column-wrap elementor-element-populated">
							<div class="elementor-widget-wrap">
						<div class="elementor-element elementor-element-457da81 elementor-widget elementor-widget-heading" data-id="457da81" data-element_type="widget" data-widget_type="heading.default">
				<div class="elementor-widget-container">
			<h2 class="elementor-heading-title elementor-size-default">Audio Title</h2>		</div>
				</div>
						</div>
					</div>
		</div>
								</div>
					</div>
		</section>
				<section class="elementor-section elementor-top-section elementor-element elementor-element-838cf02 elementor-section-boxed elementor-section-height-default elementor-section-height-default" data-id="838cf02" data-element_type="section">
						<div class="elementor-container elementor-column-gap-default">
							<div class="elementor-row">
					<div class="elementor-column elementor-col-50 elementor-top-column elementor-element elementor-element-c958111" data-id="c958111" data-element_type="column">
			<div class="elementor-column-wrap elementor-element-populated">
							<div class="elementor-widget-wrap">
						<div class="elementor-element elementor-element-50bba9a elementor-widget elementor-widget-image" data-id="50bba9a" data-element_type="widget" data-widget_type="image.default">
				<div class="elementor-widget-container">
								<div class="elementor-image">
												<img src="https://skittykat.cc/wp-content/uploads/2020/12/big-sis-blowjob-1024x576.png" class="attachment-large size-large" alt="" loading="lazy" srcset="https://skittykat.cc/wp-content/uploads/2020/12/big-sis-blowjob-1024x576.png 1024w, https://skittykat.cc/wp-content/uploads/2020/12/big-sis-blowjob-300x169.png 300w, https://skittykat.cc/wp-content/uploads/2020/12/big-sis-blowjob-768x432.png 768w, https://skittykat.cc/wp-content/uploads/2020/12/big-sis-blowjob-1536x864.png 1536w, https://skittykat.cc/wp-content/uploads/2020/12/big-sis-blowjob-533x300.png 533w, https://skittykat.cc/wp-content/uploads/2020/12/big-sis-blowjob.png 1920w" sizes="(max-width: 1024px) 100vw, 1024px" width="1024" height="576">														</div>
						</div>
				</div>
						</div>
					</div>
		</div>
				<div class="elementor-column elementor-col-50 elementor-top-column elementor-element elementor-element-b386d5f" data-id="b386d5f" data-element_type="column">
			<div class="elementor-column-wrap elementor-element-populated">
							<div class="elementor-widget-wrap">
						<div class="elementor-element elementor-element-eb42f52 elementor-widget elementor-widget-wp-widget-media_audio" data-id="eb42f52" data-element_type="widget" data-widget_type="wp-widget-media_audio.default">
				<div class="elementor-widget-container">
			<!--[if lt IE 9]><script>document.createElement('audio');</script><![endif]-->
<span class="mejs-offscreen">Audio Player</span><div id="mep_0" class="mejs-container mejs-container-keyboard-inactive wp-audio-shortcode mejs-audio" tabindex="0" role="application" aria-label="Audio Player" style="width: 495.5px; height: 40px; min-width: 239px;"><div class="mejs-inner"><div class="mejs-mediaelement"><mediaelementwrapper id="audio-1920-1"><audio class="wp-audio-shortcode" id="audio-1920-1_html5" preload="none" style="width: 100%; height: 100%;" src="https://skittykat.cc/wp-content/uploads/2020/12/HBG_Audio-Title%E2%80%8B.mp3?_=1"><source type="audio/mpeg" src="https://skittykat.cc/wp-content/uploads/2020/12/HBG_Audio-Title​.mp3?_=1"><source type="audio/mpeg" src="https://skittykat.cc/wp-content/uploads/2020/12/HBG_Audio-Title​.mp3?_=1"><a href="https://skittykat.cc/wp-content/uploads/2020/12/HBG_Audio-Title​.mp3">https://skittykat.cc/wp-content/uploads/2020/12/HBG_Audio-Title​.mp3</a></audio></mediaelementwrapper></div><div class="mejs-layers"><div class="mejs-poster mejs-layer" style="display: none; width: 100%; height: 100%;"></div></div><div class="mejs-controls"><div class="mejs-button mejs-playpause-button mejs-play"><button type="button" aria-controls="mep_0" title="Play" aria-label="Play" tabindex="0"></button></div><div class="mejs-time mejs-currenttime-container" role="timer" aria-live="off"><span class="mejs-currenttime">00:00</span></div><div class="mejs-time-rail"><span class="mejs-time-total mejs-time-slider"><span class="mejs-time-buffering" style="display: none;"></span><span class="mejs-time-loaded"></span><span class="mejs-time-current"></span><span class="mejs-time-hovered no-hover"></span><span class="mejs-time-handle"><span class="mejs-time-handle-content"></span></span><span class="mejs-time-float" style="display: none; left: 0px;"><span class="mejs-time-float-current">00:00</span><span class="mejs-time-float-corner"></span></span></span></div><div class="mejs-time mejs-duration-container"><span class="mejs-duration">00:00</span></div><div class="mejs-button mejs-volume-button mejs-mute"><button type="button" aria-controls="mep_0" title="Mute" aria-label="Mute" tabindex="0"></button></div><a class="mejs-horizontal-volume-slider" href="javascript:void(0);" aria-label="Volume Slider" aria-valuemin="0" aria-valuemax="100" aria-valuenow="100" role="slider"><span class="mejs-offscreen">Use Up/Down Arrow keys to increase or decrease volume.</span><div class="mejs-horizontal-volume-total"><div class="mejs-horizontal-volume-current" style="left: 0px; width: 100%;"></div><div class="mejs-horizontal-volume-handle" style="left: 100%;"></div></div></a></div></div></div>		</div>
				</div>
				<div class="elementor-element elementor-element-cad082a elementor-widget elementor-widget-text-editor" data-id="cad082a" data-element_type="widget" data-widget_type="text-editor.default">
				<div class="elementor-widget-container">
								<div class="elementor-text-editor elementor-clearfix">
				<blockquote class="_28lDeogZhLGXvE95QRPeDL"><p class="_1qeIAgB0cPwnLhDF9XSiJM"><span style="text-align: inherit;">Silly little brother! You don’t need the blue pill, you need a blowjob!</span></p></blockquote><p style="font-style: normal; font-variant-ligatures: normal; font-variant-caps: normal; font-weight: 400; font-size: 17px; font-family: 'System Fonts', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen-Sans, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif; text-indent: 0px;"><span style="font-weight: bold;">Script:</span> HornyGoodBoy</p><p><b>Note:</b> This audio was originally on Pornhub prior to the Dec 2020 purge.</p>					</div>
						</div>
				</div>
						</div>
					</div>
		</div>
								</div>
					</div>
		</section>
				<section class="elementor-section elementor-top-section elementor-element elementor-element-b142f1e elementor-section-boxed elementor-section-height-default elementor-section-height-default" data-id="b142f1e" data-element_type="section">
						<div class="elementor-container elementor-column-gap-default">
							<div class="elementor-row">
					<div class="elementor-column elementor-col-100 elementor-top-column elementor-element elementor-element-be1e16f" data-id="be1e16f" data-element_type="column">
			<div class="elementor-column-wrap elementor-element-populated">
							<div class="elementor-widget-wrap">
						<div class="elementor-element elementor-element-3ffba53 elementor-widget elementor-widget-wp-widget-tag_cloud" data-id="3ffba53" data-element_type="widget" data-widget_type="wp-widget-tag_cloud.default">
				<div class="elementor-widget-container">
			<h5>tags</h5><div class="tagcloud"><a href="https://skittykat.cc/tag/aftercare/" class="tag-cloud-link tag-link-120 tag-link-position-1" style="font-size: 9.7818181818182pt;" aria-label="aftercare (14 items)">aftercare</a>
</div>
		</div>
				</div>
						</div>
					</div>
		</div>
								</div>
					</div>
		</section>
						</div>"""


def test_extractor_skittykat_unicode_url(monkeypatch):
    # patch get_html to return site with embedded audio that has a zero width space
    # inside the src url
    mock_get_html = lambda cls, url, hdrs=None: (SKITTY_U200B_HTML, 200)
    monkeypatch.setattr('gwaripper.extractors.skittykat.SkittykatExtractor.get_html',
                        mock_get_html)
    extr = SkittykatExtractor("https://skittykat.cc/gonewildaudio/fskdfal-fsdkfls/")
    assert extr.content_category == 'gonewildaudio'

    fc, report = extr._extract()

    assert fc.title == "Audio Title"
    assert fc.author == "skitty-gwa"
    assert len(fc.children) == 1
    # correctly escaped
    assert fc.children[0].direct_url == (
            "https://skittykat.cc/wp-content/uploads/2020/12/HBG_Audio-Title%E2%80%8B.mp3?_=1")


erocast_expected = {
    "id":392, "mp3":0, "waveform":0, "preview":0, "wav":0, "flac":0, "hd":0, "hls":1,
    "title":"A Teacher's Voice - A Naughty Boy",
    "description":"Our teacher comes up with a way to get back at the coach for his disobedience..\n\nScript u/StoryWeaver83",
    "duration":645, "released_at":"11/22/2021",
    "permalink_url":"https://erocast.me/track/392/a-teachers-voice-a-naughty-boy",
    "streamable": True,
    "user":{"id":83, "name":"Wkdfaerie", "username":"wkdfaerie", "artist_id":0}
}

def test_extractor_erocast():
    extr = ErocastExtractor("https://erocast.me/track/392/a-teachers-voice-a-naughty-boy")
    assert extr.id == str(erocast_expected['id'])

    fi, report = extr._extract()

    assert fi.title == erocast_expected['title']
    assert fi.descr == erocast_expected['description']
    assert re.match(r"https://erocast\..*/555083/track.m3u8", fi.direct_url)
    user = erocast_expected['user']
    assert fi.author == user['name']
    assert fi.download_type == DownloadType.HLS
    assert fi.ext == "mp4"

whyp_private_expected = {
    "id":38334,
    "title":"Power Bottom Girlfriend Wants You for Breakfast",
    "slug":"power-bottom-girlfriend-wants-you-for-breakfast",
    "descr":"[F4M] Power Bottom Girlfriend Wants You for Breakfast [Wholesome] [Morning!] [Rape] cuz [Sleep play BJ] [Edging] [Needy] [Cowgirl] [Pls don’t cum inside] [Begging] [Brat actually wants your cum] [Wet sounds] [Leg locked] [Creampie] [Cuddles] [How ‘bout them pancakes?] [Script fill]: aurallyinclined\n\nSocials:\nhttps://www.youtube.com/c/skittykat\nhttps://twitter.com/SkittyKatVA\nhttps://www.patreon.com/skittykat\nhttps://www.skittykat.cc",
    "duration":1040.56,
    "direct_url":"https://cdn.whyp.it/dbcc9d2c-2ce8-486b-bf98-48ef48505e07.mp3",
    "artwork_url":"https://cdn.whyp.it/79855dfd-435a-45ee-9de0-9fc9d42cb8bb.png",
    "created_at":"2022-08-25T18:45:52+00:00",
    "user_id":4384,
    "tags":[],
    "token":"yAtIM",
    "public": False,
    "allow_downloads": False,
    "settings_comments":"users",
    "nsfw": True,
    "author":"skittykat",
    "avatar":"https://cdn.whyp.it/f713e761-d9f4-4e2b-bf43-8eafc6713b7b.png",
    "cover":"https://cdn.whyp.it/a68db4ae-7447-4aa0-8a12-58fdbcb7d9ed.png",
}

def test_extractor_whyp_private_no_token(caplog):
    extr = WhypExtractor("https://whyp.it/tracks/38334/power-bottom-girlfriend-wants-you-for-breakfast")
    assert extr.id == str(whyp_private_expected['id'])
    assert extr.token is None

    caplog.clear()
    caplog.set_level(logging.WARNING)
    fi, report = extr._extract()
    assert report.err_code is ExtractorErrorCode.NO_RESPONSE
    assert "missing the token" in caplog.text
    assert fi is None

def test_extractor_whyp_private():
    url = "https://whyp.it/tracks/38334/power-bottom-girlfriend-wants-you-for-breakfast?token=yAtIM"
    extr = WhypExtractor(url)
    assert extr.id == str(whyp_private_expected['id'])
    assert extr.token == whyp_private_expected['token']

    fi, report = extr._extract()
    assert report.err_code is ExtractorErrorCode.NO_ERRORS
    assert fi is not None

    assert fi.page_url == url
    assert fi.ext == "mp3"
    assert fi.download_type is DownloadType.HTTP

    for k in ("title", "descr", "direct_url", "author"):
        assert getattr(fi, k) == whyp_private_expected[k]

whyp_public_expected = {
        "id":38357,
        "title":"Your Big Sister's Hot Roommate Seduces You And Takes Your Virginity",
        "descr": json.loads(r'["Original Script by u/ScriptsFromaSub\n\nBecome a Patron to access my full library of original, high quality audios: patreon.com/SooJeong\n\n\u1d1b\u029c\u026a\ua731 \u1d00\u1d1c\u1d05\u026a\u1d0f \u1d0d\u1d00\u028f \u1d04\u1d0f\u0274\u1d1b\u1d00\u026a\u0274 \u1d04\u1d0f\u1d18\u028f\u0280\u026a\u0262\u029c\u1d1b \u1d0d\u1d1c\ua731\u026a\u1d04 \u1d00\u0274\u1d05 \ua731\ua730x \u1d21\u029c\u026a\u1d04\u029c \u026a, \u1d1b\u029c\u1d07 \u1d18\u1d07\u0280\ua730\u1d0f\u0280\u1d0d\u1d07\u0280 (\ua731\u1d0f\u1d0f\u1d0a\u1d07\u1d0f\u0274\u0262), \u1d00\u1d0d \u029f\u1d07\u0262\u1d00\u029f\u029f\u028f \u1d00\u1d1c\u1d1b\u029c\u1d0f\u0280\u026a\u1d22\u1d07\u1d05 \u1d1b\u1d0f \u1d1c\ua731\u1d07. \u1d05\u1d0f \u0274\u1d0f\u1d1b \u1d04\u1d0f\u1d18\u028f, \u1d07\u1d05\u026a\u1d1b, \u1d0f\u0280 \u0280\u1d07\u1d1c\u1d18\u029f\u1d0f\u1d00\u1d05 \u1d0d\u028f \u1d04\u1d0f\u0274\u1d1b\u1d07\u0274\u1d1b \u1d21\u026a\u1d1b\u029c\u1d0f\u1d1c\u1d1b \u1d07x\u1d18\u029f\u026a\u1d04\u026a\u1d1b \u1d04\u1d0f\u0274\ua731\u1d07\u0274\u1d1b."]')[0],
        "duration":1619.98,
        "direct_url":"https://cdn.whyp.it/e2c8515a-bc1e-4613-886a-6b2d89f4c56f.mp3",
        "artwork_url":"https://cdn.whyp.it/cd530d16-d734-4222-b0f9-86164bfa55a3.jpg",
        "created_at":"2022-08-25T21:04:02+00:00",
        "user_id":4497,
        "tags":[],
        "token":"I3Eo3",
        "public":True,
        "author":"SooJeong",
        "avatar":"https://cdn.whyp.it/4b1a5fe6-834f-4bf9-9a91-9a7b338733c3.jpg",
        "cover":"https://cdn.whyp.it/177b90b0-56a9-4d7b-9cd8-f8fd5770bbc5.jpg"
}

def test_extractor_whyp_public():
    url = "https://whyp.it/tracks/38357/your-big-sisters-hot-roommate-seduces-you-and-takes-your-virginity"
    extr = WhypExtractor(url)
    assert extr.id == str(whyp_public_expected['id'])
    assert extr.token is None

    fi, report = extr._extract()
    assert report.err_code is ExtractorErrorCode.NO_ERRORS
    assert fi is not None

    assert fi.page_url == url
    assert fi.ext == "mp3"
    assert fi.download_type is DownloadType.HTTP

    for k in ("title", "descr", "direct_url", "author"):
        assert getattr(fi, k) == whyp_public_expected[k]


import pytest
import logging
import os
import time
import shutil

import gwaripper.config as config

from gwaripper.reddit import reddit_praw
from gwaripper.extractors import find_extractor
from gwaripper.extractors.soundgasm import SoundgasmExtractor
from gwaripper.extractors.eraudica import EraudicaExtractor
from gwaripper.extractors.chirbit import ChirbitExtractor
from gwaripper.extractors.imgur import ImgurImageExtractor, ImgurAlbumExtractor
from gwaripper.extractors.reddit import RedditExtractor, check_submission_banned_tags
from gwaripper.info import FileInfo
from utils import setup_tmpdir


@pytest.mark.parametrize(
        'url, expected, attr_val',
        [('https://soundgasm.net/user/DDCherryB/Tantus-Toy-Review', SoundgasmExtractor,
          {'is_user': False, 'author': 'DDCherryB'}),
         ('https://soundgasm.net/u/tarkustrooper/F-Journey-of-The-Sorcerer-by-The-Eagles'
          '-excerpt-cover', SoundgasmExtractor,
          {'is_user': False, 'author': 'tarkustrooper'}),
         ('https://soundgasm.net/u/belle_in_the_woods/F4M-Kiss-Me-Touch-Me-Take-Me-From-Behind-'
          'spooning-sexpillow-bitingcreampiebeggingmaking-outkissinggropingdry-humpingwhispers',
          SoundgasmExtractor, {'is_user': False, 'author': 'belle_in_the_woods'}),
         ('https://soundgasm.net/u/test-1234/', SoundgasmExtractor,
          {'is_user': True, 'author': 'test-1234'}),
         ('https://soundgasm.net/user/SAfs_05dfas', SoundgasmExtractor,
          {'is_user': True, 'author': 'SAfs_05dfas'}),
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
         ('https://i.imgur.com/gBDbyOY.png', ImgurImageExtractor,
          {'ext': 'png', 'is_direct': True, 'image_hash': 'gBDbyOY'}),
         ('https://imgur.com/Eg34A9f', ImgurImageExtractor,
          {'ext': None, 'is_direct': False, 'image_hash': 'Eg34A9f'}),
         ('https://imgur.com/gallery/WUgRi', ImgurAlbumExtractor, {'album_hash': 'WUgRi'}),
         ('https://imgur.com/gallery/h2fJ8Nq', ImgurAlbumExtractor, {'album_hash': 'h2fJ8Nq'}),
         ('reddit.com/r/gonewildaudio/comments/5oeedy/f4m_six_months_after_my_'
          'break_up_friends_to/', RedditExtractor, {}),
         ('http://reddit.com/r/gonewildaudio/comments/5j6rf5/f4m_mars_colonization/',
          RedditExtractor, {}),
         ('https://old.reddit.com/r/pillowtalkaudio/comments/44vvko/f4m_scriptfill_a_'
          'gift_lbombs_kisses_giggles/', RedditExtractor, {}),
         ('https://www.reddit.com/r/gonewildaudio/comments/4r44q5/f4m_its_a_sassapalooza_'
          '4_new_audios_scripts_by', RedditExtractor, {}),
         ('https://chirb.it/hnze3A/sdjkfas', None, None),
         ('https://youtube.com/watch?v=32ksdf83', None, None),
         ('http://reddit.com/r/gonewildaudio/', None, None),
         ('http://reddit.com/user/gwarip/', None, None),
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


class Submission:
    def __init__(self, title):
        self.title = title
        self.shortlink = "testing"


@pytest.mark.parametrize("title, keywordlist, tag1_but_not_2, expected", [
    ("[M4F] This should be banned", ["[m4", "[cuck"], None, True),
    ("[M4F] This shouldnt be banned", ["[cuck", "cei"], None, False),
    ("[F4M] This should also be banned [cuck]", ["[m4", "[cuck"], None, True),
    ("[F4F] This should be banned", ["[m4", "[cuck"], [("[f4f]", "4m]")], True),
    ("[F4F][F4M] This shouldnt be banned", ["[m4", "[cuck"], [("[f4f]", "4m]")], False)
])
def test_banned_tags(title, keywordlist, tag1_but_not_2, expected):
    # simulate reddit sub
    sub = Submission(title)
    result = check_submission_banned_tags(sub, keywordlist, tag1_but_not_2)
    assert result == expected


def test_soundgasm_user_extractor(monkeypatch):
    ex = SoundgasmExtractor("https://soundgasm.net/u/DDCherryB")
    # otherwise _extract_user will extract all files from the ONLINE website
    monkeypatch.setattr('gwaripper.extractors.soundgasm.SoundgasmExtractor._extract_file',
                        lambda x: FileInfo(x.__class__, True, None, x.url,
                                           None, None, None, None, None))
    fcol = ex.extract()
    # sgasm_usr_audio_urls should be last urls on user page
    assert sgasm_usr_audio_urls == [c.page_url for c in fcol.children][-len(sgasm_usr_audio_urls):]


def test_extractor_soundgasm():
    # user tested above already
    url = ("https://soundgasm.net/u/kinkyshibby/F4M-Queen-of-the-Black-"
           "Coast-Pirate-Queen-Barbarian-Warrior-Seduction-Erotic-Dance-Sultry-Seriously-"
           "Extremely-Sultry-Exhibitionism-Mild-Fdom-Creampie-Script-Fill")

    ex = SoundgasmExtractor(url)
    assert not ex.is_user
    assert ex.author == "kinkyshibby"
    fi = ex.extract()

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
    assert fi.downloaded is False
    assert fi.already_downloaded is False


def test_extractor_eraudica():
    url1 = "https://www.eraudica.com/e/eve/2018/Sweeter-Nothings-Sexy-Time"
    url2 = "https://www.eraudica.com/e/eve/2018/Sweeter-Nothings-Sexy-Time/gwa"

    ex = EraudicaExtractor(url1)
    assert ex.url == url1
    fi = ex.extract()

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
    assert fi.downloaded is False
    assert fi.already_downloaded is False

    ex = EraudicaExtractor(url2)
    # should alway be without /gwa postfix!
    assert ex.url == url1


def test_extractor_chirbit():
    url = "https://chirb.it/F5hInh"

    ex = ChirbitExtractor(url)
    assert ex.url == url
    fi = ex.extract()

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
    assert fi.downloaded is False
    assert fi.already_downloaded is False


def test_extractor_imgur_image():
    url = 'https://i.imgur.com/c0T9oSy.mp4'  # mp4

    ex = ImgurImageExtractor(url)
    assert ex.direct_url == url
    assert ex.url == "https://imgur.com/c0T9oSy"
    assert ex.ext == 'mp4'
    assert ex.is_direct is True
    assert ex.image_hash == "c0T9oSy"
    fi = ex.extract()

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
    assert fi.downloaded is False
    assert fi.already_downloaded is False

    # url = 'https://i.imgur.com/gBDbyOY.png'  # png
    url = 'https://imgur.com/Ded3OiN'  # marked as mature

    ex = ImgurImageExtractor(url)
    assert ex.url == url
    assert ex.ext is None
    assert ex.is_direct is False
    assert ex.image_hash == "Ded3OiN"
    fi = ex.extract()

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
    assert fi.downloaded is False
    assert fi.already_downloaded is False


def test_extractor_imgur_album(monkeypatch):
    url = 'https://imgur.com/a/OPqcLpw'  # 3 jpg images

    ex = ImgurAlbumExtractor(url)
    ex.album_hash = "OPqcLpw"
    fcol = ex.extract()
    ex.image_count = 3
    ex.title = "Testing album"

    assert fcol.url == url
    assert fcol.id == "OPqcLpw"
    assert fcol.title == "Testing album"

    # NOTE: only check that we get the correct urls/hashes for the images
    # in the ablum the rest is already being tested by test_extractor_imgur_image
    monkeypatch.setattr('gwaripper.extractors.imgur.ImgurImageExtractor.extract',
                        lambda x: FileInfo(x.__class__, None, None, x.url,
                                           x.direct_url, None, None, None, None))

    img_urls = (
        ('https://imgur.com/hnDOLrH', 'https://i.imgur.com/hnDOLrH.jpg'),
        ('https://imgur.com/G52dEpB', 'https://i.imgur.com/G52dEpB.jpg'),
        ('https://imgur.com/ozozXyN', 'https://i.imgur.com/ozozXyN.jpg')
    )
    for i, img in enumerate(fcol.children):
        assert img.parent is fcol
        assert img.page_url == img_urls[i][0]
        assert img.direct_url == img_urls[i][1]

    # NOTE: currently always getting mp4 for all animated sources
    url = 'https://imgur.com/a/tcl9AuW'  # gif, webm+sound, mp4

    ex = ImgurAlbumExtractor(url)
    ex.album_hash = "tcl9AuW"
    fcol = ex.extract()
    ex.image_count = 3
    ex.title = "Test album animated ?"

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
    for i, img in enumerate(fcol.children):
        assert img.parent is fcol
        assert img.page_url == animated_urls[i][0]
        assert img.direct_url == animated_urls[i][1]


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
        ("https://www.reddit.com/r/gonewildaudio/comments/ewco8n/"
         "becoming_the_lamia_tribehusband_ffff4m/",  # 1 sg link in text + imgur album
         ["https://soundgasm.net/u/POVscribe/Becoming-the-Lamia-Tribe-Husband-FFFF4MMonstergirls",
          "https://imgur.com/a/4iaKN9F"],
         {
             # fcol
             "url": ('https://www.reddit.com/r/gonewildaudio/comments/ewco8n/'
                     'becoming_the_lamia_tribehusband_ffff4m/'),
             "id": 'ewco8n',
             "title": ("Becoming the Lamia Tribe-Husband [FFFF4M] [Monstergirls][4 Lusty "
                       "Lamia Ladies][Fivesome/Orgy][Aphrodisiac Venom][Fdom]and[Fsub]"
                       "[Deflowering][Blowjob][Facial][Many Creampies][Impreg][Breeding]"
                       "[MoreTagsBelow][Collab] with /u/AuralAllusions /u/DanseuseElectrique "
                       "/u/valeriethinevalkyrie"),
             "author": "POVscribe",
             # ri
             "permalink": ("/r/gonewildaudio/comments/ewco8n/"
                           "becoming_the_lamia_tribehusband_ffff4m/"),
             "selftext": """^(More tags: \\[Multiple orgasms\\]\\[Fingering\\]\\[Cunnilingus\\]\\[Taking Turns\\]\\[Multiple Positions\\])\n\n**Premise**: A well-known mercenary gets invited to a remote desert town for a special contract. When he arrives, he learns the town is a small tribal [lamia](https://imgur.com/a/4iaKN9F) queendom, whose queen has a very special offer for him….\n\n4 lusty Lamia ladies assemble to fill this [script](https://www.reddit.com/r/gonewildaudio/comments/e4495x/becoming_the_lamia_tribehusbandscript/) offered by u/RamblingKnight.\n\n**LISTEN**: [**Becoming the Lamia Tribe-Husband**](https://soundgasm.net/u/POVscribe/Becoming-the-Lamia-Tribe-Husband-FFFF4MMonstergirls) {41 min}\n\n"*You will give up your old life to come live here, and be the father of our children. You will devote the rest of your life to mating with us.…..*\n\n*…..and of course satiate our tribe’s ……every desire….."*\n\n\\+ + + + + + +\n\n**CAST**:\n\nDiana, our Queen, u/AuralAllusions\n\nKassia, Captain of the Guard, by u/POVscribe\n\nSophia, the court priestess, by u/DanseuseElectrique\n\nEris, the Queen\'s concubine, by u/valeriethinevalkyrie\n\n**PRODUCTION**:\n\nSound Editor/Mixer: u/Kilbeggan32 (Want to sound *this* good? Check out his [page](https://www.reddit.com/r/Kilbeggan32/) to learn more.)\n\nProject Manager: u/POVscribe\n\nAll music/sounds are copyright/royalty-free.\n\n\\+ + + + + + +\n\n^(A wholly fictional fantasy made by, about, and for adults 18+)""",
             "created_utc": 1580419842.0,
             "subreddit": "gonewildaudio",
             "r_post_url": ("https://www.reddit.com/r/gonewildaudio/comments/ewco8n/"
                            "becoming_the_lamia_tribehusband_ffff4m/"),
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


class DummyExtractor():
    EXTRACTOR_NAME = "Dummy"
    BASE_URL = "dummy.org"

    def __init__(self, url):
        self.url = url

    def extract(self):
        return FileInfo(self.__class__, True, None, self.url,
                        None, None, None, None, None)


def test_extractor_reddit(setup_tmpdir, monkeypatch, caplog):
    # NOTE: use DummyExtractor since we only care about the extracted urls
    # but make sure to still return RedditExtractor since that is used
    # to avoid extracting forther reddit submissions
    backup_find = find_extractor  # save orig func
    mock_findex = lambda x: (RedditExtractor if RedditExtractor.is_compatible(x)
                             else DummyExtractor)
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

    tmpdir = setup_tmpdir
    linkcoldir = os.path.join(tmpdir, "_linkcol")

    caplog.set_level(logging.INFO)
    for url, found_urls, attr_val_dict in reddit_extractor_url_expected:
        # important that actual extractors are tested since
        # we apparently expect RedditInfo to be None which is the case
        # for banned keywords or not finding supported AUDIO urls
        if attr_val_dict is None:
            monkeypatch.setattr('gwaripper.extractors.find_extractor', backup_find)

            try:
                shutil.rmtree(linkcoldir)
            except FileNotFoundError:
                pass

        ex = RedditExtractor(url)

        caplog.clear()
        ri = ex.extract()

        if attr_val_dict is not None:
            for attr_name, value in attr_val_dict.items():
                assert getattr(ri, attr_name) == value

            # IMPORTANT check that parent and reddit_info was set
            for child in ri.children:
                assert child.parent is ri
        elif type(found_urls) is str:
            assert ri is None
            # shortlink written to html
            fn = f"reddit_nurl_{time.strftime('%Y-%m-%d_%Hh.html')}"
            fn = os.path.join(linkcoldir, fn)
            with open(fn, 'r') as f:
                contents = f.read()
            assert ("/r/gonewildaudio/comments/69evvm/"
                    "f4mcougarstrangers_a_new_neighbor_moves_in_next/") in contents
            # make sure follow-up tests don't write to the same file
            os.remove(fn)
        else:
            msg = caplog.records[0].message
            assert "https://redd.it/4r33ek" in msg
            assert msg.startswith("Banned keyword: no '[script fill]' in title "
                                  "where '[script offer]' is in")
            assert ri is None

        # restore patched version for other tests
        if attr_val_dict is None:
            monkeypatch.setattr('gwaripper.extractors.find_extractor', mock_findex)

    #
    # test using a praw submission instead of url
    #
    r = reddit_praw()
    sub = r.submission(id=reddit_extractor_url_expected[0][2]['id'])

    # pass in old.reddit.com... url and submission object
    ex = RedditExtractor(reddit_extractor_url_expected[0][0], sub)

    caplog.clear()
    ri = ex.extract()

    for attr_name, value in reddit_extractor_url_expected[0][2].items():
        assert getattr(ri, attr_name) == value

    # IMPORTANT check that parent and reddit_info was set
    for child in ri.children:
        assert child.parent is ri

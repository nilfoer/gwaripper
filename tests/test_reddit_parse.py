import pytest
from gwaripper.gwaripper import parse_submissions_for_links, check_submission_banned_tags, get_sub_from_reddit_urls

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


@pytest.fixture
def get_subs_adls():
    urls = [
        # sg in url
        "https://www.reddit.com/r/gonewildaudio/comments/6c49gk/f4m_im_your_pornstar_cumdumpster_slut_mother/",
        # chirbit url
        "https://www.reddit.com/r/gonewildaudio/comments/3rtfxc/ff4m_its_not_what_you_think_brother_age_rape/",
        # eraudica in url
        "https://www.reddit.com/r/gonewildaudio/comments/3gs9dm/f4m_nurse_eve_time_for_your_physical/",
        # sg in text
        "https://www.reddit.com/r/gonewildaudio/comments/6b7aux/f4m_please_make_me_a_mommy_impregwet/",
        # chirbit in text
        "https://www.reddit.com/r/gonewildaudio/comments/5k3k41/f4m_my_virginity_will_be_your_christmas_present/",
        # eraudica in text
        "https://www.reddit.com/r/gonewildaudio/comments/6b5j18/f4m_nurse_eve_and_dr_eve_double_team_tlc/",
        # no url found
        "https://www.reddit.com/r/gonewildaudio/comments/4r33ek/f4m_a_lesbian_does_her_male_friend_a_favor_script/"
    ]

    r_found_urls = {
        urls[0]: "https://soundgasm.net/u/miyu213/F4M-Im-your-Pornstar-Cumdumpster-Slut-Mother-RapeBlackmailFacefuckingSlap-my-face-with-that-thick-cockInnocent-to-sluttyRoughDirty-TalkFuck-Me-Into-The-MatressCreampieImpregMultiple-Real-Orgasms",
        urls[1]: "http://chirb.it/s80vbt",
        urls[2]: "http://eraudica.com/e/eve/2015/Nurse-Eve-Time-For-Your-Physical",
        urls[3]: "https://soundgasm.net/u/belle_in_the_woods/F4M-Please-Make-Me-a-Mommy-impregwet-soundscreampiefuck-me-deeppaint-my-insidesdirty-talkbeggingwhispersASMRstereo-recording",
        urls[4]: "http://chirb.it/Op55m7",
        urls[5]: "https://www.eraudica.com/e/eve/2015/Twin-TLC-Dr-Eve-and-Nurse-Eve-a-Sucking-Fucking-Hospital-Romp",
    }

    sublist = get_sub_from_reddit_urls(urls)
    return sublist, r_found_urls


def test_parse_sub(get_subs_adls):
    sublist, found_man = get_subs_adls
    result = parse_submissions_for_links(sublist, True)
    # TODO only checking page url not rest of AudioDownload: host, reddit_info
    assert len(result) == len(found_man) + 1 # since in post there are 2 sgasm urls (identical)
    for adl in result:
        assert found_man["https://www.reddit.com{}".format(adl.reddit_info["permalink"])] == adl.page_url


class Submission:
    def __init__(self, title):
        self.title = title
        self.shortlink = "testing"
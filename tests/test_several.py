import pytest
from gwaripper.gwaripper import rip_usr_links

# urrlib can also get html code from disk with file:///
# so we can test if all links are found, getting it frome the server could mean they were files added
# and wed have to update our test, but justing with this means we wouldnt notice the code on server changing
# -> test getting all links from disk html, and test the links from now contained in links we got online

# expected = [
#     'https://soundgasm.net/u/DDCherryB/Youve-got-another-girl-somewhere-beastmaybe-DDLGno-age-rapecrying-l-bombsimpreg-surprise-lube-sounds-big-cock-stretching-Ill-take-it-like-a-big-girl',
#     'https://soundgasm.net/u/DDCherryB/You-are-getting-sleepy-no-piano',
#     'https://soundgasm.net/u/DDCherryB/Tantus-Toy-Review',
#     'https://soundgasm.net/u/DDCherryB/You-are-getting-sleepy',
#     'https://soundgasm.net/u/DDCherryB/Much-needed-shameless-masturbation',
#     'https://soundgasm.net/u/DDCherryB/Crusader',
#     'https://soundgasm.net/u/DDCherryB/Panty-sniffer',
#     'https://soundgasm.net/u/DDCherryB/Best-friends-to-lovers',
#     'https://soundgasm.net/u/DDCherryB/Mermaids-blowjob',
#     'https://soundgasm.net/u/DDCherryB/Verification-try-2',
#     'https://soundgasm.net/u/DDCherryB/Verification-and-Script-Fill']

expected_man = [
    "https://soundgasm.net/u/DDCherryB/Youve-got-another-girl-somewhere-beastmaybe-DDLGno-age-rapecrying-l-bombsimpreg-surprise-lube-sounds-big-cock-stretching-Ill-take-it-like-a-big-girl",
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


def test_rip_usrlinks_off():
    urls = rip_usr_links("file:///N:/_archive/test/trans/soundgasmNET/_dev/_sgasm-repo/tests/test_res/DDCherryB_ripuser_soundgasm.net.html")
    # make sure list have same contents, wont change since from file
    assert expected_man == urls


def test_rip_usrlinks_on():
    urls = rip_usr_links("https://soundgasm.net/u/DDCherryB")
    # make sure every url we expect (got them manually from site) is in found urls
    for url in expected_man:
        assert url in urls
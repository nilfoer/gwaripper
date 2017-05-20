import pytest  # for fixture otherwise not needed
from gwaripper.gwaripper import append_new_info_downloaded, AudioDownload, filter_alrdy_downloaded

@pytest.fixture
def create_df_dl_dict():
    import pandas as pd
    df_dummy = pd.DataFrame(
        data=[['Date', 'Description: DummyLine', 'Local_filename', 'Time', 'Title: DummyTitle', 'URL',
               'URLsg', 'redditURL', 'sgasm_user', 'reddit_user', 0, 'redditTitle',
               1234.0, 'redditID', 'subredditName', 'rPostUrl']],
        columns=['Date', 'Description', 'Local_filename', 'Time', 'Title', 'URL',
                 'URLsg', 'redditURL', 'sgasm_user', 'reddit_user', 'filenr', 'redditTitle',
                 'created_utc', 'redditID', 'subredditName', 'rPostUrl'])
    reddit_info = {"title": "testtitle", "permalink": "testperm",
                   "selftext": "testself", "r_user": "testruser",
                   "created_utc": 12345.0, "id": "test123",
                   "subreddit": "testsub", "r_post_url": "testpurl"}
    reddit_info2 = {"title": "testtitle2", "permalink": "testperm2",
                    "selftext": "testself2", "r_user": "testruser2",
                    "created_utc": 123456.0, "id": "test1232",
                    "subreddit": "testsub2", "r_post_url": "testpurl2"}
    adl = AudioDownload("https://soundsm.net/u/testu1/test1", "sgasm", reddit_info=reddit_info)
    adl.url_to_file = "testfile"
    adl.downloaded = True
    adl.title = "testtit"
    adl.filename_local = "testfn"
    adl.descr = "testdescr"
    adl.date = "testd"
    adl.time = "testt"
    adl2 = AudioDownload("https://soundgasm.net/u/testu2/test2", "sgasm", reddit_info=reddit_info2)
    adl2.url_to_file = "testfile2"
    adl2.downloaded = True
    adl2.title = "testtit2"
    adl2.filename_local = "testfn2"
    adl2.descr = "testdescr2"
    adl2.date = "testd2"
    adl2.time = "testt2"
    dl_dict = {"https://soundsm.net/u/testu1/test1": adl,
               "https://soundgasm.net/u/testu2/test2": adl2}
    return df_dummy, dl_dict


@pytest.fixture
def create_df_append():
    import pandas as pd
    from numpy import nan

    df_dummy, dl_dict = create_df_dl_dict()

    # manually created df to match
    df_appended = pd.DataFrame(
        data=[['Date', 'Description: DummyLine', 'Local_filename', 'Time', 'Title: DummyTitle', 'URL',
               'URLsg', 1234.0, 0, 'rPostUrl', 'redditID', 'redditTitle', 'redditURL', 'reddit_user', 'sgasm_user',
               'subredditName'],
              ['testd', 'testdescr', 'testfn', 'testt', 'testtit', 'testfile',
               'https://soundsm.net/u/testu1/test1', 12345.0, nan, 'testpurl', 'test123', 'testtitle',
               'testperm', 'testruser', 'testu1', 'testsub'],
              ['testd2', 'testdescr2', 'testfn2', 'testt2', 'testtit2', 'testfile2',
               'https://soundgasm.net/u/testu2/test2', 123456.0, nan, 'testpurl2', 'test1232', 'testtitle2',
               'testperm2', 'testruser2', 'testu2', 'testsub2']],
        columns=['Date', 'Description', 'Local_filename', 'Time', 'Title', 'URL',
                 'URLsg', 'created_utc', 'filenr', 'rPostUrl', 'redditID', 'redditTitle',
                 'redditURL', 'reddit_user', 'sgasm_user','subredditName'])

    new_dls = ["https://soundsm.net/u/testu1/test1", "https://soundgasm.net/u/testu2/test2"]

    # also use append to create df to match
    # df_append_dict = {"Date": ["testd", "testd2"], "Time": ["testt", "testt2"], "Local_filename": ["testfn", "testfn2"],
    #                   "Description": ["testdescr", "testdescr2"], "Title": ["testtit", "testtit2"], "URL": ["testfile", "testfile2"],
    #                   "URLsg": ["https://soundsm.net/u/testu1/test1", "https://soundgasm.net/u/testu2/test2"],
    #                   "sgasm_user": ["testu1", "testu2"], "redditURL": ["testperm", "testperm2"],
    #                   "reddit_user": ["testruser", "testruser2"], "redditTitle": ["testtitle", "testtitle2"],
    #                   "created_utc": [12345.0, 123456.0], "redditID": ["test123", "test1232"],
    #                   "subredditName": ["testsub", "testsub2"], "rPostUrl": ["testpurl", "testpurl2"]}
    #
    # df_dict = pd.DataFrame.from_dict(df_append_dict)
    # df_appended = df_dummy.append(df_dict, ignore_index=True, verify_integrity=True)

    return df_dummy, new_dls, dl_dict, df_appended

def test_append_new_info(create_df_append):
    df_dummy, new_dls, dl_dict, df_appended = create_df_append
    df_t = append_new_info_downloaded(df_dummy, new_dls, dl_dict)
    assert df_appended.equals(df_t)


def test_filter_dl(create_df_dl_dict):
    df_dummy, dl_dict = create_df_dl_dict
    df = df_dummy.copy()
    # set url of dummy line to one of the urls in dldict so it gets filtered; soundsm due to set_missing_values stuff
    df.set_value(0, "URLsg", "https://soundsm.net/u/testu1/test1")
    filtered = filter_alrdy_downloaded(df, dl_dict)
    assert filtered == ["https://soundgasm.net/u/testu2/test2"]


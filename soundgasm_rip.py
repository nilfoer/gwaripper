#! python3
import urllib.request
import re
import os
import time
import clipwatcher_single
import praw
import bs4
import logging, logging.handlers
import sys

user_agent = "gwaRipper"
# changed
reddit_praw = praw.Reddit(user_agent=user_agent)

# banned TAGS that will exclude the file from being downloaded (when using reddit)
# removed: "[daddy]", 
KEYWORDLIST = ["[m4", "[m]", "[request]", "[script offer]", "[cbt]",
               "[ce]", "[cei]", "[cuck]", "[f4f]"]
# path to dir where the soundfiles will be stored in subfolders
ROOTDIR = os.path.abspath(os.path.join(os.getcwd(), os.pardir))
# old os.path.join("N:", os.sep, "_archive", "test", "soundgasmNET")
# old (os.sep, "home", "m", "Dokumente", "test-sg")

# configure logging
#logfn = time.strftime("%Y-%m-%d.log")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# create a file handler
handler = logging.handlers.TimedRotatingFileHandler("gwaripper.log", "D", encoding="UTF-8", backupCount=10)
handler.setLevel(logging.DEBUG)

# create a logging format
formatter = logging.Formatter("%(asctime)-15s - %(name)-9s - %(levelname)-6s - %(message)s")
#'%(asctime)s - %(name)s - %(levelname)s - %(message)s'
handler.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(handler)

# create streamhandler
stdohandler = logging.StreamHandler(sys.stdout)
stdohandler.setLevel(logging.INFO)

# create a logging format
formatterstdo = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%H:%M:%S")
stdohandler.setFormatter(formatterstdo)
logger.addHandler(stdohandler)


def main():
    opt = input("Was moechten Sie tun?\n\n 1. Rip/Update Users\n 2. Rip from single links\n "
                "3. Rip single links from a txt file\n 4. Watch clipboard for sgasm links\n "
                "5. Watch clipboard for reddit links\n 6. Download sgasm posts from subreddit\n "
                "7. Rip single reddit links from a txt file\n 8. Subreddit durchsuchen und Ergebnisse "
                "herunterladen\n")
    if opt == "1":
        usrurls = input("Enter soundgasm User URLs separated by \",\" - no spaces\n")
        rip_users(usrurls)
        main()
    elif opt == "2":
        links = input("Enter soundgasm post URLs separated by \",\" - no spaces\n")
        rip_from_links(links)
        main()
    elif opt == "3":
        txtfn = input("Enter filename of txt file containing post URLs separated by newlines\n")
        mypath = os.path.join(ROOTDIR, "_linkcol")
        rip_from_links(txt_to_list(mypath, txtfn))
        main()
    elif opt == "4":
        watch_clip("sgasm")
        main()
    elif opt == "5":
        watch_clip("reddit")
        main()
    elif opt == "6":
        subr = input("Enter subreddit name: \n")
        limit = input("Enter post-limit: \n")
        links = parse_submissions_for_links(parse_subreddit(subr, int(limit)))
        #rip_from_links_reddit(links)
        #write_last_dltime()
        main()
    elif opt == "7":
        txtfn = input("Enter filename of txt file containing post URLs separated by newlines\n")
        llist = get_sub_from_reddit_urls(txt_to_list(os.path.join(ROOTDIR, "_linkcol"), txtfn))
        links = parse_submissions_for_links(llist, True)
        rip_from_links_reddit(links)
        main()
    elif opt == "8":
        subname = input("Enter name of subreddit\n")
        limit = input("Enter limit for found submissions, max 1000 forced by Reddit:\n")
        searchstring = input("Enter search string:\n")
        found_subs = search_subreddit(subname, searchstring, limit=limit)
        links = parse_submissions_for_links(found_subs, True)
        #rip_from_links_reddit(links)
        main()


def rip_users(sgusr_urls):
    # trennt user url string an den kommas
    sgusr_urllist = sgusr_urls.split(",")
    for usr in sgusr_urllist:
        # geht jede url in der liste durch entfernt das komma und gibt sie an rip_usr_to_files weiter
        rip_usr_to_files(usr.strip(","))


def txt_to_list(path, txtfilename):
    with open(os.path.join(path, txtfilename), "r", encoding="UTF-8") as f:
            llist = f.read().split()
            return llist


def get_sub_from_reddit_urls(urllist):
    sublist = []
    for url in urllist:
        # changed
        sublist.append(reddit_praw.get_submission(url=url))
    return sublist


def rip_from_links(sglinks):
    # .copy()?
    sglinkslist = sglinks
    if isinstance(sglinks, str):
        sglinkslist = sglinks.split(",")
    # anzahl eintraege in der liste ergeben anzahl der zu ladenden dateien
    dlcounter = 0
    filestodl = len(sglinkslist)
    for link in sglinkslist:
        # teilt string in form von https://soundgasm.net/u/USERNAME/link-to-post an /u/,
        # so erhaelt man liste mit https://soundgasm.net/u/, USERNAME/link-to-post
        # wird weiter an / geteilt aber nur ein mal und man hat den username
        currentusr = link.split("/u/", 1)[1].split("/", 1)[0]
        txtfilename = "sgasm-" + currentusr + "-rip.txt"
        downloaded_urls = load_downloaded_urls(txtfilename, currentusr)
        riptuple = rip_link_furl(link.strip(","))
        erg = rip_file(riptuple, txtfilename, currentusr, dlcounter, filestodl, downloaded_urls, True)
        dlcounter = erg[0]
        filestodl = erg[1]


# TODO refactor merge with above
def rip_from_links_reddit(sglinks):
    # anzahl eintraege in der liste ergeben anzahl der zu ladenden dateien
    dlcounter = 0
    filestodl = len(sglinks)
    for link in sglinks:
        # teilt string in form von https://soundgasm.net/u/USERNAME/link-to-post an /u/,
        # so erhaelt man liste mit https://soundgasm.net/u/, USERNAME/link-to-post
        # wird weiter an / geteilt aber nur ein mal und man hat den username
        currentusr = link[0].split("/u/", 1)[1].split("/", 1)[0]
        txtfilename = "sgasm-" + currentusr + "-rip.txt"
        downloaded_urls = load_downloaded_urls(txtfilename, currentusr)
        riptuple = rip_link_furl(link[0])
        erg = rip_file(riptuple, txtfilename, currentusr, dlcounter, filestodl, downloaded_urls, True, redditurl=link[1])
        dlcounter = erg[0]
        filestodl = erg[1]


def rip_usr_to_files(sgasm_usr_url):
    user_files = rip_usr_links(sgasm_usr_url)
    # zeit bei anfang des dl in variable schreiben
    now = time.strftime("%d/%m/%Y %H:%M:%S")
    currentusr = sgasm_usr_url.split("/u/", 1)[1].split("/", 1)[0]
    logger.info("Ripping user %s" % currentusr)
    txtfilename = "sgasm-" + currentusr + "-rip.txt"
    downloaded_urls = load_downloaded_urls(txtfilename, currentusr)
    dlcounter = 0
    filestodl = len(user_files)
    userrip_string = ""
    for afile in user_files:
        riptuple = rip_link_furl(afile)
        erg = rip_file(riptuple, txtfilename, currentusr, dlcounter, filestodl, downloaded_urls, False, userrip_string)
        dlcounter = erg[0]
        filestodl = erg[1]
    # falls dateien beim user rip geladen wurden wird der string in die textdatei geschrieben
    if dlcounter > 0:
        write_to_txtf("User Rip von " + currentusr + " mit " + str(dlcounter) + " neuen Dateien" + " am " + now +
                      "\n\n" + userrip_string, txtfilename, currentusr)


def rip_usr_links(sgasm_usr_url):
    site = urllib.request.urlopen(sgasm_usr_url)
    html = site.read().decode('utf-8')
    site.close()
    # links zu den einzelnen posts isolieren
    nhtml = html.split("<div class=\"sound-details\"><a href=\"")
    del nhtml[0]
    user_files = []
    for splits in nhtml:
        # teil str in form von https://soundgasm.net/u/USERNAME/link-to-post> an ">" und schreibt
        # den ersten teil in die variable url
        url = splits.split("\">", 1)[0]
        # url in die liste anfuegen
        user_files.append(url)
    filestodl = len(user_files)
    logger.info("Found " + str(filestodl) + " Files!!")
    return user_files


def rip_link_furl(sgasmurl):
    logger.info("Ripping %s" % sgasmurl)
    try:
        site = urllib.request.urlopen(sgasmurl)
        html = site.read().decode('utf-8')
        site.close()
        nhtml = html.split("aria-label=\"title\">")
        title = nhtml[1].split("</div>", 1)[0]
        #descript = nhtml[1].split("Description: ")[1].split("</li>\r\n", 1)[0]
        descript = nhtml[1].split("<div class=\"jp-description\">\r\n          <p style=\"white-space: pre-wrap;\">")[1].split("</p>\r\n", 1)[0]
        urlm4a = nhtml[1].split("m4a: \"")[1].split("\"\r\n", 1)[0]

        return title, descript, sgasmurl, urlm4a
    except urllib.request.HTTPError:
            logger.warning("HTTP Error 404: Not Found: \"%s\"" % sgasmurl)


def rip_file(riptuple, txtfilename, currentusr, curfnr, maxfnr,
             downloaded_urls, single=True, usrrip_string="", redditurl=""):
    if riptuple is not None:
        if not check_file_for_dl(riptuple[3], downloaded_urls, txtfilename, currentusr):
            curfnr += 1
            if single:
                write_to_txtf("\tAdded: " + time.strftime("%d/%m/%Y %H:%M:%S") + "\n\n\tTitle: " +
                              riptuple[0] + ",\n\tDescription: " + riptuple[1] + ",\n\tURL: \"" +
                              riptuple[3] + "\",\n\tURLsg: \"" + riptuple[2] + "\",\n", txtfilename, currentusr)
                if redditurl is not None:
                    write_to_txtf("\tredditURL: \"" + redditurl + "\",\n", txtfilename, currentusr)
            else:
                usrrip_string += "\tTitle: " + riptuple[0] + ",\n\t" + "Description: " + riptuple[1] + ",\n\t" + "URL: \"" \
                                 + riptuple[3] + "\",\n\t" + "URLsg: \"" + riptuple[2] + "\",\n"

            # append url to downloaded_urls so we dont miss duplicate urls in the same download session
            downloaded_urls.append(riptuple[3])

            filename = re.sub("[^\w\-_\.,\[\] ]", "_", riptuple[0][0:110]) + ".m4a"
            mypath = os.path.join(ROOTDIR, currentusr)
            if not os.path.exists(mypath):
                os.makedirs(mypath)
            i = 0
            if os.path.isfile(os.path.join(mypath, filename)):
                logger.info("FILE ALREADY EXISTS - RENAMING:")
            while os.path.isfile(os.path.join(mypath, filename)):
                i += 1
                filename = re.sub("[^\w\-_\.,\[\] ]", "_", riptuple[0][0:106]) + "_" + str(i).zfill(3) + ".m4a"
            logger.info("Downloading: " + filename + ", File " + str(curfnr) + " of " + str(maxfnr))
            if single:
                write_to_txtf("\tLocal filename: \"" + filename + "\"\n\t" + ("___" * 30) + "\n\n\n", txtfilename,
                              currentusr)
            else:
                usrrip_string += "\tLocal filename: \"" + filename + "\"\n\t" + ("___" * 30) + "\n\n\n"
            try:
                urllib.request.urlretrieve(riptuple[3], os.path.abspath(os.path.join(mypath, filename)))
            except urllib.request.HTTPError:
                logger.warning("HTTP Error 404: Not Found: \"%s\"" % riptuple[3])

            return curfnr, maxfnr, usrrip_string
        else:
            maxfnr -= 1
            logger.info("File already downloaded - Skipping: " + riptuple[0])
            return curfnr, maxfnr, usrrip_string
    else:
        maxfnr -= 1
        logger.warning("FILE DOWNLOAD SKIPPED - NO DATA RECEIVED")
        return curfnr, maxfnr, usrrip_string


def write_to_txtf(wstring, filename, currentusr):
    mypath = os.path.join(ROOTDIR, currentusr)
    if not os.path.exists(mypath):
        os.makedirs(mypath)
    with open(os.path.join(mypath, filename), "a", encoding="UTF-8") as w:
        w.write(wstring)

def load_downloaded_urls(txtfilename, currentusr):
    downloaded_urls = []
    if os.path.isfile(os.path.join(mypath, txtfilename)):
        with open(os.path.join(mypath, txtfilename), 'r', encoding="UTF-8") as f:
            read_data = f.read()
            urllist = read_data.split("URL: \"")
            del urllist[0]
            for url in urllist:
                downloaded_urls.append(url.split("\"", 1)[0])
    return downloaded_urls

def check_file_for_dl(m4aurl, downloaded_urls, txtfilename, currentusr):
    """
    Returns True if file was already downloaded
    :param m4aurl: direct URL to m4a file
    :param downloaded_urls: list of already downloaded m4a urls
    :param txtfilename: name of txtfile
    :param currentusr: name of curren user
    :return: True if m4aurl is in downloaded_urls, else False
    """
    if m4aurl in downloaded_urls:
        return True
    else:
        return False


def watch_clip(domain):
    dm = eval("clipwatcher_single.is_" + domain + "_url")
    watcher = clipwatcher_single.ClipboardWatcher(dm, clipwatcher_single.print_write_to_txtf, 0.1)
    try:
        logger.info("Watching clipboard...")
        watcher.run()
    except KeyboardInterrupt:
        watcher.stop()
        logger.info("Stopped watching clipboard!")


def parse_subreddit(subreddit, limit):
    sub = reddit_praw.get_subreddit(subreddit)
    return sub.get_hot(limit=limit)

def search_subreddit(subname, searchstring, limit=100, sort="top", **kwargs):
    # sort: relevance, hot, top, new, comments (default: relevance).
    # syntax: cloudsearch, lucene, plain (default: lucene)
    # time_filter – Can be one of: all, day, hour, month, week, year (default: all)
    subreddit = reddit_praw.get_subreddit(subname)

    found_sub_list = []

    # Returns a generator for submissions that match the search query
    matching_sub_gen = subreddit.search(searchstring, sort=sort, period="all", limit=limit, **kwargs)
    # iterate over generator and append found submissions to list
    for sub in matching_sub_gen:
        found_sub_list.append(sub)
    return found_sub_list



def parse_submissions_for_links(sublist, fromtxt=False):
    url_list = []
    lastdltime = get_last_dltime()
    for submission in sublist:
        if (not check_submission_banned_tags(submission, KEYWORDLIST) and
                (fromtxt or check_submission_time(submission, lastdltime))):
            if "soundgasm.net" in submission.url:
                url_list.append((submission.url, str(submission.permalink)))
                logger.info("Link found in URL of: " + submission.title)
                check_new_redditor(submission.url, str(submission.author))
            elif (submission.selftext_html is not None) and ("soundgasm.net" in submission.selftext_html):
                soup = bs4.BeautifulSoup(submission.selftext_html, "html.parser")

                # selects all anchors(a) with href attribute that contains "soundgasm.net/u/"
                # ^= is for begins with, $= is for ends with, *= is for is in
                # select returns them as tag objects
                sgasmlinks = soup.select('a[href*="soundgasm.net/u/"]')
                uchecked = False
                for link in sgasmlinks:
                    usrcheck = re.compile("/u/.+/.+", re.IGNORECASE)
                    if usrcheck.search(link["href"]):
                        # appends href-attribute of tag object link
                        url_list.append((link["href"], str(submission.permalink)))
                        logger.info("SGASM link found in text, in submission: " + submission.title)
                        if not uchecked:
                            check_new_redditor(link["href"], str(submission.author))
                            uchecked = True
            else:
                logger.info("No soundgsam link in \"" + submission.short_link + "\"")
                with open(os.path.join(ROOTDIR, "_linkcol", "reddit_nurl_" + time.strftime("%Y-%m-%d_%Hh.html")),
                          'a', encoding="UTF-8") as w:
                    w.write("<h3><a href=\"" + submission.permalink + "\">" + submission.title + "</a><br/>by " +
                            str(submission.author) + "</h3>\n")
    return url_list


def check_new_redditor(url, username):
    currentusr = url.split("/u/", 1)[1].split("/", 1)[0]
    filename = "reddit_u_" + username + ".txt"
    # check for reddit_u_USERNAME.txt
    # if os.path.isfile(ROOTDIR, currentusr, #FILENAME)
    if os.path.exists(os.path.join(ROOTDIR, currentusr)):
        return True
    else:
        write_to_txtf(username, filename, currentusr)
        return False


def check_submission_banned_tags(submission, keywordlist):
    # checks submissions title for banned words contained in keywordlist
    # returns True if it finds a match
    for keyword in keywordlist:
        if keyword in submission.title.lower():
            logger.info("Banned keyword in: " + submission.title.lower() + "\n\t slink: " + submission.short_link)
            return True


def write_last_dltime():
    if not os.path.exists(ROOTDIR):
        os.makedirs(ROOTDIR)
    with open(os.path.join(ROOTDIR, "LASTDLTIME.TXT"), "w") as w:
        w.write(str(time.time()))


def get_last_dltime():
    with open(os.path.join(ROOTDIR, "LASTDLTIME.TXT"), "r") as w:
        return float(w.read())


def check_submission_time(submission, lastdltime):
    if submission.created_utc > lastdltime:
        logger.info("Submission is newer than lastdltime")
        return True
    else:
        logger.info("Submission is older than lastdltime")
        return False

if __name__ == "__main__":
    main()

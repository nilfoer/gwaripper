import os
import re
import numpy as np
import pandas as pd
import pprint

ROOT_DIR = os.path.abspath(os.path.join(os.getcwd(), os.pardir))

def get_files_to_parse():
    user_files = []
    # iterate over ROOT_DIR contents
    for f in os.listdir(ROOT_DIR):
        # if its a dir
        if os.path.isdir(os.path.join(ROOT_DIR, f)):
            dltxt_path = os.path.join(ROOT_DIR, f, "sgasm-{}-rip.txt".format(f))
            # if dltxt exists in that dir add it to user_files with full path
            if os.path.isfile(dltxt_path):
                user_files.append(dltxt_path)
    return user_files

def _get_date(linecont):
    line_cont = linecont
    # match ^beginning of string \d+ one or more digtis whitespace Dateien
    p = re.compile("^\d+ Dateien")

    if line_cont.startswith("\tAdded:"):
        # Added: DD/MM/YYYY HH:MM:SS
        # 0      1          2
        # pass slice [1:3] endpoint not incl
        return line_cont.split()[1:3]
    elif line_cont.startswith("User Rip von"):
        return line_cont.split()[9:11]
    elif re.match(p, line_cont):
        # split at whitespaces including \t
        return line_cont.split()[2:3]
    else:
        return

df_dict = {"Date": [], "Time": [], "Title": [], "Description": [],
           "URL": [], "URLsg": [], "redditURL": [], "Local_filename": [] }

with open("N:\\_archive\\test\\trans\\soundgasmNET\\_dev\\BadGirlUK\\sgasm-BadGirlUK-rip.txt", "r") as f:
    # every line as list element
    lines = f.read().splitlines()

# remove empty strings form list with filter
# Python 3 returns an iterator from filter, so should be wrapped in a call to list()
lines = list(filter(None, lines))

date = None
title = ""
descr = ""
url = ""
url_sg = ""
r_url = ""
loc_fn = ""

for line in lines:
    # get date -> None if not contained in line
    new_date = _get_date(line)
    # if not none -> set date
    if new_date:
        date = new_date
        # if new date was found -> line alrdy processed -> next line
        continue
    if line.startswith("\tTitle: "):
        # strip remove given string at beginning and end of string
        title = line.strip(",")[8:]
    elif line.startswith("\tDescription: "):
        descr = line.strip(",")[14:]
    elif line.startswith("\tURL: "):
        # remove ", at end of str
        url = line.strip("\",")[7:]
    elif line.startswith("\tURLsg: "):
        url_sg = line.strip("\",")[9:]
    elif line.startswith("\tredditURL: "):
        r_url = line.strip("\",")[13:]
    elif line.startswith("\tLocal filename: "):
        # split at " -> Local filename: "filename.m4a" -> ["Local...", "filename.m4a", "" or ","]
        # TODO mb use for other urls as well?
        loc_fn = line.split("\"")[1]
    elif line.startswith("\t________"):
        # entry for file is over -> append to lists in dict and reset vars
        df_dict["Date"].append(date[0])
        if len(date) > 1:
            df_dict["Time"].append(date[1])
        else:
            df_dict["Time"].append("")
        df_dict["Title"].append(title)
        df_dict["Description"].append(descr)
        df_dict["URL"].append(url)
        df_dict["URLsg"].append(url_sg)
        df_dict["redditURL"].append(r_url)
        df_dict["Local_filename"].append(loc_fn)
        # np.nan or ""?
        title = descr = url = url_sg = r_url = loc_fn = ""
    else:
        descr += "\n" + line.strip(",")

df = pd.DataFrame.from_dict(df_dict)
df.to_csv("../BadGirlUK/info.csv", sep=";")
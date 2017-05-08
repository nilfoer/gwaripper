import os
import re
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.getcwd(), os.pardir, os.pardir))

# using re.compile() and saving the resulting regular expression object for reuse is more efficient when
# the expression will be used several times in a single program
# match ^beginning of string \d+ one or more digtis whitespace Dateien
# match alrdy only matches at beginning of str, so ^ is redundant
PATTERN_OLD_DATE = re.compile("^\d+ Dateien")
PATTER_ADDED_DATE = re.compile("^\s?Added: \d{2}/\d{2}/\d{4}")


def get_files_to_parse():
    user_files = []
    # iterate over ROOT_DIR contents
    for f in os.listdir(ROOT_DIR):
        # if its a dir
        if os.path.isdir(os.path.join(ROOT_DIR, f)):
            dltxt_path = os.path.join(ROOT_DIR, f, "sgasm-{}-rip.txt".format(f))
            # if dltxt exists in that dir add it to user_files with full path
            if os.path.isfile(dltxt_path):
                r_user = ""
                # get reddit user name
                for fn in os.listdir(os.path.join(ROOT_DIR, f)):
                    if fn.startswith("reddit_u_"):
                        with open(os.path.join(ROOT_DIR, f, fn), "r", encoding="UTF-8") as r:
                            r_user = r.read().strip()
                user_files.append([dltxt_path, f, r_user])
    return user_files


def _get_date(linecont):
    line_cont = linecont

    if re.match(PATTER_ADDED_DATE, line_cont):
        # ^stringstart \s whitespace 0 or 1 Added:..
        # match alrdy
        # old line_cont.startswith("\tAdded:")
        # Added: DD/MM/YYYY HH:MM:SS
        # 0      1          2
        # pass slice [1:3] endpoint not incl
        return line_cont.split()[1:3]
    elif line_cont.startswith("User Rip von"):
        return line_cont.split()[9:11]
    elif re.match(PATTERN_OLD_DATE, line_cont):
        # split at whitespaces including \t
        date = line_cont.split()[2:3]
        # sometimes the date is missing, need to return sth thats not None
        if date:
            return date
        else:
            return ["None"]
    else:
        return


def gen_dict_from_dltxt(fullpath, user, r_user):
    df_dict = {"Date": [], "Time": [], "Title": [], "Description": [],
               "URL": [], "URLsg": [], "redditURL": [], "Local_filename": []}

    with open(fullpath, "r", encoding="UTF-8") as f:
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
    # add user col and set same val for all rows
    df['sgasm_user'] = user
    df['reddit_user'] = r_user
    # add row with continuous filenr
    df["filenr"] = range(len(df["Title"]))

    return df


def main():
    users_to_parse = get_files_to_parse()
    # creat first df that other will be appended to
    # unpack list into args
    df = gen_dict_from_dltxt(*users_to_parse.pop(0))

    for usr in users_to_parse:
        # It is worth noting however, that concat (and therefore append) makes a full copy of the data, and that
        # constantly reusing this function can create a significant performance hit. If you need to use the operation
        # over several datasets, use a list comprehension.
        df = df.append(gen_dict_from_dltxt(*usr), ignore_index=True)

    df.to_csv("../test.csv", sep=";", encoding="utf-8")

if __name__ == "__main__":
    main()
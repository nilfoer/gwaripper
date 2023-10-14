"""
File: webGUI.py
Description: Creates a webGUI for GWARipper using flask
"""

import os
import re
import datetime

from typing import Optional, List, Tuple, Dict, Any, NamedTuple

from flask import (
    current_app, request, redirect, url_for, Blueprint,
    render_template, flash, send_from_directory,
    jsonify, send_file, session, g, Response, abort
)
from werkzeug.utils import secure_filename

from gwaripper.gwaripper import GWARipper
from gwaripper import config
from gwaripper.db import (
    get_x_entries, validate_order_by_str, search,
    remove_entry as gwa_remove_entry, set_favorite_entry,
    set_rating, RowData
)
from gwaripper.info import sanitize_filename, FileInfo, FileCollection
from gwaripper.extractors.base import BaseExtractor

from .gwaripper_db import get_db

ENTRIES_PER_PAGE = 30

# no url prefix
main_bp = Blueprint("main", __name__)

URL_RE = re.compile(r"(?:https?://)?(?:\w+\.)?(\w+\.\w+)/")
ALLOWED_EXTENSIONS = {"m4a", "mp4", "webm", "aac", "mp3", "flv", "avi", "mpeg", "mkv", "ogg",
                      "oga", "mogg", "act", "flac", "mpc", "opus", "wav", "wma"}


def init_app(app):
    # send that we accept byte ranges for sending partial content
    @app.after_request
    def after_request(response):
        response.headers.add('Accept-Ranges', 'bytes')
        return response

    return None


# BUG: the server gets "stuck" while sending an audio file and won't repsond to any requests
# need to have multiple files that are playing or started playing and were then paused
# sometimes seeking to a different place in the audio file on the client fixes it
# flask still responds to a new request since reloading the page or opening
# a new one works but when opening a new one in the debugger it crashes inside
# the jinja code? in show_entries.html on the entry title div

# not the cause for this ^ bug or at least both 'solutions' don't fix
# flask send_from_directory just sends the whole file to the client, which can cause
# freezes esp. in single threaded mode
# to solve this either use multi-threaded mode (not tested if this acutally solves it)
# the other solution is sending partial content as in send byte ranges of files
# the client first has to know that the server supports it so the server can send
# "Accept-Ranges": "bytes" as part of the header
# the client can then send "Content-Range": bytes startbyte- or startbyte-endbyte
# see: https://codeburst.io/the-taste-of-media-streaming-with-flask-cdce35908a50
#      https://stackoverflow.com/questions/57314357/streaming-video-files-using-flask


# this and part of artist_file from https://stackoverflow.com/a/57324447
# by waynetech
def get_chunk(filename, byte1=None, byte2=None):
    file_size = os.stat(filename).st_size
    start = 0
    # roughly 6secs for a 128kBit/s mp3 file
    chunk_size = 102400

    if byte1 < file_size:
        start = byte1
    if byte2:
        # byte-pos is 0-based
        chunk_size = byte2 + 1 - byte1
    else:
        chunk_size = file_size - start

    with open(filename, 'rb') as f:
        f.seek(start)
        chunk = f.read(chunk_size)
    return chunk, start, chunk_size, file_size


# browser sends open-ended request 0- but not the whole file is sent
# https://stackoverflow.com/a/61755095
# However, examples of ServiceWorkers responding to Range Requests (Safari
# browser) suggests that the expected response to open-ended requests like 0-
# is the entire byte range. Browsers then stream the response up to some
# heuristic, and if the user seeks to a range outside of what has been streamed
# the initiate a subsequent open-ended request.
#
# if there's a file with 1000 bytes: the first request is always Range:
# bytes=0-. The browser decides to load 100 bytes. The user seeks toward the
# end, and the browser sends another request Range: bytes=900-.

# create route for artist files/static data that isnt in static, can be used in template with
# /audio/artist/filename or with url_for(main.artist_file, artist='artist', filename='filename')
# Custom static data
@main_bp.route('/artist_file/<path:filename>')
def artist_file(filename):
    range_header = request.headers.get('Range', None)
    subpath = request.args.get('subpath', '')

    first_byte, last_byte = 0, None
    if range_header:
        # https://tools.ietf.org/html/rfc7233#section-4.2
        # * if complete-length unknown
        # byte-pos is 0-based
        # request: byte-range = first-byte-pos "-" last-byte-pos
        # / without "" means alternative "/" is a literal /
        # () forms a group
        # response: byte-range "/" ( complete-length / "*" )
        # or on 416 (Range Not Satisfiable): unsatisfied-range = "*/" complete-length

        # starts with "bytes " or "bytes=" even though rfc7233 only specifies SP (space)
        start_first_byte = next(
            i for i, c in enumerate(range_header) if c.isdigit())
        first_byte_str, last_byte_str = range_header[start_first_byte:].split(
            '-')
        first_byte = int(first_byte_str)
        if last_byte_str:
            last_byte = int(last_byte)

    full_path = os.path.join(current_app.instance_path, subpath, filename)
    try:
        chunk, start, chunk_size, file_size = get_chunk(
            full_path, first_byte, last_byte)
    except FileNotFoundError:
        abort(404)

    # mimetype should be type/subtype;parameter=value
    resp = Response(chunk, 206, mimetype='audio',
                    content_type='audio', direct_passthrough=True)
    # byte-pos is 0-based
    resp.headers.add(
        'Content-Range', f"bytes {start}-{start + chunk_size - 1}/{file_size}")

    # TODO send 416 with unsatisfied-range if we can't provide the range that was requested
    return resp


@main_bp.route('/embed/audio/<path:filename>')
def embed_audio(filename: str):
    subpath = request.args.get('subpath', '')

    full_path = os.path.join(current_app.instance_path, subpath, filename)
    if not os.path.exists(full_path):
        return (
            "Local file couldn't be found, use the link to "
            "the source page (world icon) instead!")
    return "".join(["<audio controls src='",
                   url_for('main.artist_file',
                           subpath=subpath, filename=filename),
                   "'></audio>"])


@main_bp.route('/embed/selftext/<path:filename>')
def embed_selftext(filename: str):
    subpath = request.args.get('subpath', '')

    if not filename:
        return "No selftext file has been saved!"

    full_path = os.path.join(current_app.instance_path, subpath, filename)
    if not os.path.exists(full_path):
        return (
            "<br/>Error: Local selftext file couldn&#39;t be found!<br/>")
    with open(full_path, 'r') as f:
        lines = f.readlines()
    return "".join(['<h2>Selftext:</h2>',
                    "<br/>".join(lines)])


# py3.6: new way to define named tuples with types using class syntax
# order of variables is also the order you pass them during initialization
# AudioPathHelper('author', 'subpath',  'self.txt')
class AudioPathHelper(NamedTuple):
    subpath: str
    selftext_filename: Optional[str]


def get_entries(query: Optional[str] = None) -> Tuple[
        List[RowData], List[AudioPathHelper], str, str, Optional[Any], Optional[Any],
        Optional[Dict[str, bool]]]:
    order_by_col = request.args.get('sort_col', "id", type=str)
    # validate our sorting col otherwise were vulnerable to sql injection
    if not validate_order_by_str(order_by_col):
        order_by_col = "id"
    asc_desc = "ASC" if request.args.get(
        'order', "DESC", type=str) == "ASC" else "DESC"
    order_by = f"AudioFile.{order_by_col} {asc_desc}"
    # dont need to validate since we pass them in with SQL param substitution
    after = request.args.getlist("after", None)
    after = after if after else None
    before = request.args.getlist("before", None)
    before = before if before else None

    # branch on condition if we have a NULL for the primary sorting col
    # order_by_col isnt id but we only got one value from after/before
    if after is not None and len(after) == 1 and order_by_col != "id":
        after = (None, after[0])
    elif before is not None and len(before) == 1 and order_by_col != "id":
        before = (None, before[0])

    entries: List[RowData]
    if query:
        # get 1 entry more than ENTRIES_PER_PAGE so we know if we need btn in that direction
        entries = search(get_db(), query, order_by=order_by,
                         limit=ENTRIES_PER_PAGE+1, after=after, before=before)
    else:
        entries = get_x_entries(get_db(), ENTRIES_PER_PAGE+1, after=after, before=before,
                                order_by=order_by)
    first, last, more = first_last_more(entries, order_by_col, after, before)

    audio_paths: List[AudioPathHelper] = []
    if entries:
        # account for older selftext filenames
        # <0.3 audio file name + '.txt'
        # ==0.3: subpath + sanitized reddit title + '.txt'
        for entry in entries:
            selftext_filename: Optional[str] = None

            if entry.collection_id is not None:
                author_subdir = entry.fcol_alias_name
                subpath = entry.fcol_subpath
            else:
                author_subdir = entry.alias_name
                subpath = ""

            # we write a selftext in set_missing_reddit even though we don't have a filename
            # but ignore that here @Incomplete
            if entry.filename and entry.fcol_id_on_page is not None:
                date: datetime.date = entry.date
                # date v0.3 started
                if date > datetime.date(year=2020, month=10, day=10):
                    # @CleanUp basically repeating code from info.py here

                    # selftext might have been added later which means it won't use
                    # fcol_alias_name etc. but just alias_name
                    # needs author_subdir to get correct length
                    selftext_filename = sanitize_filename(
                        os.path.join(author_subdir, subpath),
                        entry.fcol_title) + '.txt'
                else:
                    selftext_filename = f"{entry.filename}.txt"

            audio_paths.append(AudioPathHelper(
                os.path.join(author_subdir, subpath).replace('\\', '/'),
                selftext_filename))

    return entries, audio_paths, order_by_col, asc_desc, first, last, more


@main_bp.route('/', methods=["GET"])
def show_entries():
    entries, audio_paths, order_by_col, asc_desc, first, last, more = get_entries()

    return render_template(
        'show_entries.html',
        display_search_err_msg=True if entries is None else False,
        entries=entries,
        audio_paths=audio_paths,
        more=more,
        first=first,
        last=last,
        order_col=order_by_col,
        asc_desc=asc_desc)


def first_last_more(entries: List[RowData], order_by_col: str = "id",
                    after: Optional[int] = None, before: Optional[int] = None) -> Tuple[
        Optional[Any], Optional[Any], Optional[Dict[str, bool]]]:
    if not entries:
        return None, None, None

    more: Dict[str, bool] = {"next": False, "prev": False}

    # we alway get one row more to know if there are more results after our current last_id
    # in the direction we moved in
    if len(entries) == ENTRIES_PER_PAGE+1:
        onemore = True
    else:
        onemore = False

    if after is None and before is None:
        # firstpage
        if onemore:
            more["next"] = True
            del entries[-1]
        else:
            more["next"] = False
    elif after is not None:
        # if we get args before/after there are more results for the opposite
        # e.g. if we get a before=61 we had to have had an after=60 that led us to that page
        more["prev"] = True
        if onemore:
            more["next"] = True
            # remove additional book
            del entries[-1]
        else:
            more["next"] = False
    elif before is not None:
        more["next"] = True
        if onemore:
            more["prev"] = True
            del entries[0]
        else:
            more["prev"] = False

    first_id = entries[0].id
    last_id = entries[-1].id
    if "id" != order_by_col.lower():
        # if we are sorting by something else than id
        # we also need to pass the values of that col
        primary_first = getattr(entries[0], order_by_col)
        primary_last = getattr(entries[-1], order_by_col)
        return (primary_first, first_id), (primary_last, last_id), more
    else:
        return first_id, last_id, more


@main_bp.route("/search", methods=["GET"])
def search_entries():
    searchstr = request.args['q']
    if URL_RE.match(searchstr):
        return redirect(url_for("main.jump_to_book_by_url", ext_url=searchstr))

    entries, audio_paths, order_by_col, asc_desc, first, last, more = get_entries(
        searchstr)

    return render_template(
        'show_entries.html',
        display_search_err_msg=True if entries is None else False,
        entries=entries,
        audio_paths=audio_paths,
        more=more,
        first=first,
        last=last,
        search_field=searchstr,
        order_col=order_by_col,
        asc_desc=asc_desc)


# function that accepts ajax request so we can add lists on show_info
# without reloading the page or going to edit
# @main_bp.route("/book/<int:book_id>/list/<action>", methods=["POST"])
# def list_action_ajax(book_id, action):
#     list_name = request.form.get("name", None, type=str)
#     # jquery will add brackets to key of ajax data of type array
#     before = request.form.getlist("before[]", type=str)
#     if list_name is None:
#         return jsonify({"error": "Missing list name from data!"})

#     if action == "add":
#         # was getting Bad Request 400 due to testing print line below:
#         # ...the issue is that Flask raises an HTTP error when it fails to find
#         # a key in the args and form dictionaries. What Flask assumes by
#         # default is that if you are asking for a particular key and it's not
#         # there then something got left out of the request and the entire
#         # request is invalid.
#         # print("test",request.form["adjak"],"test")
#         Book.add_assoc_col_on_book_id(get_mdb(), book_id, "list", [list_name], before)
#         # pass url back to script since we cant use url_for
#         return jsonify({"added": list_name,
#                         "search_tag_url": url_for('main.search_entries',
#                                                   q=f'tag:"{list_name}"')})
#     elif action == "remove":
#         Book.remove_assoc_col_on_book_id(get_mdb(), book_id, "list", [list_name], before)
#         return jsonify({"removed": list_name})
#     else:
#         return jsonify({
#             "error": f"Supplied action '{action}' is not a valid list action!"
#             })


@main_bp.route("/entry/set-favorite", methods=("POST",))
def set_favorite():
    entry_id = request.form.get("entryId", None, type=int)
    fav_intbool = request.form.get("favIntbool", None, type=int)
    if entry_id is None or fav_intbool is None:
        return jsonify({"error": "Missing entry id or fav value from data!"})
    set_favorite_entry(get_db(), entry_id, fav_intbool)
    return jsonify({})


@main_bp.route("/entry/rate", methods=("POST",))
def rate_entry():
    entry_id = request.form.get("entryId", None, type=int)
    rating = request.form.get("rating", None, type=float)
    if entry_id is None:
        return render_template(
            'components/entry_rate.html',
            rate_error='Error: Failed to update rating! Missing entry id!')
    if rating is None:
        return render_template(
            'components/entry_rate.html',
            rate_error='Error: Failed to update rating! Missing rating!')

    set_rating(get_db(), entry_id, rating)
    return render_template(
        'components/entry_rate.html',
        entry={'id': entry_id, 'rating': rating})


@main_bp.route('/entry/<int:entry_id>', methods=("DELETE",))
def remove_entry(entry_id: int):
    gwa_remove_entry(get_db(), entry_id, current_app.instance_path)
    return (
        '<div class="red-fcolor">Entry was successfully removed from the DB! '
        'You have to delete the files manually!</div>')


@main_bp.route("/entry/add")
def show_add_audio():
    new_info = FileInfo(BaseExtractor, True, "", "", "",
                        None, "New Audio", None, None)
    db = get_db()
    c = db.execute("SELECT name FROM Artist")
    artists = [r['name'] for r in c.fetchall()]

    return render_template(
        'edit_audio.html',
        artists=artists,
        file_info=new_info)


@main_bp.route("/entry/add/submit", methods=("POST",))
def add_audio():
    # check if the post request has the file part
    if 'file' not in request.files:
        flash("Missing file")
        return redirect(url_for('main.show_entries'))
    file_data = request.files['file']
    # if user does not select file, browser also
    # submit an empty part without filename
    if file_data.filename == '':
        flash("Missing file")
        return redirect(url_for('main.show_entries'))

    try:
        extension = file_data.filename.rsplit(".", 1)[1]
    except (IndexError, AttributeError):
        flash("Could not parse file extension from uploaded file!")
        return redirect(url_for('main.show_add_audio'))
    else:
        if extension not in ALLOWED_EXTENSIONS:
            flash("Upload of files with this extension is not allowed!")
            return redirect(url_for('main.show_add_audio'))

    new_info = FileInfo(BaseExtractor, True, extension, request.form['page_url'], '', request.form.get('id'),
                        request.form['title'], request.form.get('description'), request.form['artist'])
    subpath, filename, extension = new_info.generate_filename(None)
    # NOTE: !IMPORTANT! since we use the title, which is passed in as user input, to compute
    # the filename, we should use sth. like werkzeug.utils.secure_filename
    # HOWEVER since we sanitize the filename in generate_filename anyway (only allowing
    # alphanum, -_.,[] and spaces) it shouldn't be necessary here
    # using it anyway to be safe
    filename = secure_filename(f"{filename}.{extension}")
    filename, extension = filename.rsplit(".", 1)

    mypath = os.path.join(config.get_root(), new_info.author, subpath)
    os.makedirs(mypath, exist_ok=True)
    filename = GWARipper._pad_filename_if_exists(mypath, filename, extension)
    filename = f"{filename}.{extension}"

    file_data.save(os.path.join(mypath, filename))

    flash("File imported successfully!")

    db = get_db()
    with db:
        # since manually added files currently don't have a FileCollection
        # we need to add the associated artist manually
        GWARipper.add_artist(db, new_info.author)
        GWARipper.add_to_db(db, new_info, None, filename,
                            file_author_is_artist=True)

    return redirect(url_for('main.show_entries'))

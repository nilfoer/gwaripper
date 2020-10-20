"""
File: webGUI.py
Description: Creates webGUI for GWARipper using flask
"""

import os.path
import re
from flask import (
        current_app, request, redirect, url_for, Blueprint,
        render_template, flash, send_from_directory,
        jsonify, send_file, session, g
)

from gwaripper.db import (
        get_x_entries, validate_order_by_str, search,
        remove_entry as gwa_remove_entry, set_favorite_entry,
        set_rating
)

from .gwaripper_db import get_db

ENTRIES_PER_PAGE = 30

# no url prefix
main_bp = Blueprint("main", __name__)

URL_RE = re.compile(r"(?:https?://)?(?:\w+\.)?(\w+\.\w+)/")


def init_app(app):
    return None


# create route for artist files/static data that isnt in static, can be used in template with
# /audio/artist/filename or with url_for(main.artist_file, artist='artist', filename='filename')
# Custom static data
@main_bp.route('/audio/<path:artist>/<path:filename>')
def artist_file(artist, filename):
    return send_from_directory(os.path.join(current_app.instance_path, artist), filename)


def get_entries(query=None):
    order_by_col = request.args.get('sort_col', "id", type=str)
    # validate our sorting col otherwise were vulnerable to sql injection
    if not validate_order_by_str(order_by_col):
        order_by_col = "id"
    asc_desc = "ASC" if request.args.get('order', "DESC", type=str) == "ASC" else "DESC"
    order_by = f"Downloads.{order_by_col} {asc_desc}"
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

    if query:
        # get 1 entry more than ENTRIES_PER_PAGE so we know if we need btn in that direction
        entries = search(get_db(), query, order_by=order_by,
                         limit=ENTRIES_PER_PAGE+1, after=after, before=before)
    else:
        entries = get_x_entries(get_db(), ENTRIES_PER_PAGE+1, after=after, before=before,
                                order_by=order_by)
    first, last, more = first_last_more(entries, order_by_col, after, before)

    return entries, order_by_col, asc_desc, first, last, more


@main_bp.route('/', methods=["GET"])
def show_entries():
    entries, order_by_col, asc_desc, first, last, more = get_entries()
    return render_template(
        'show_entries.html',
        display_search_err_msg=True if entries is None else False,
        entries=entries,
        more=more,
        first=first,
        last=last,
        order_col=order_by_col,
        asc_desc=asc_desc)


def first_last_more(entries, order_by_col="id", after=None, before=None):
    if not entries:
        return None, None, None

    more = {"next": None, "prev": None}

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

    entries, order_by_col, asc_desc, first, last, more = get_entries(searchstr)

    return render_template(
        'show_entries.html',
        display_search_err_msg=True if entries is None else False,
        entries=entries,
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
    if entry_id is None or rating is None:
        return jsonify({"error": "Missing entry id or rating from data!"})
    set_rating(get_db(), entry_id, rating)
    return jsonify({})


@main_bp.route('/entry/remove', methods=("POST",))
def remove_entry():
    entry_id = request.form.get("entryId", None, type=int)
    if entry_id is None:
        return jsonify({"error": "Missing entry id from data!"})
    success = gwa_remove_entry(get_db(), entry_id, current_app.instance_path)
    return jsonify({"removed": success})

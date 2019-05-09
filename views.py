from flask import make_response
from flask import request
from flask import abort
from flask import render_template
from flask import jsonify
from sqlalchemy import orm

import json
import os
import logging
import sys
import requests
import re
import random
from time import time

from pub import Pub
from pub import DoiLookup

from app import app
from app import db
from pub_list import PubList
from search import fulltext_search_title
from search import get_synonym
from search import get_nerd_term_lookup
from annotation import annotation_file_contents
from util import elapsed
from util import clean_doi
from util import get_sql_answers
from util import str_to_bool
from util import clean_doi


# try it at https://api.paperbuzz.org/v0/doi/10.1371/journal.pone.0000308

def json_dumper(obj):
    """
    if the obj has a to_dict() function we've implemented, uses it to get dict.
    from http://stackoverflow.com/a/28174796
    """
    try:
        return obj.to_dict()
    except AttributeError:
        return obj.__dict__


def json_resp(thing):
    json_str = json.dumps(thing, sort_keys=True, default=json_dumper, indent=4)

    if request.path.endswith(".json") and (os.getenv("FLASK_DEBUG", False) == "True"):
        print u"rendering output through debug_api.html template"
        resp = make_response(render_template(
            'debug_api.html',
            data=json_str))
        resp.mimetype = "text/html"
    else:
        resp = make_response(json_str, 200)
        resp.mimetype = "application/json"
    return resp


def abort_json(status_code, msg):
    body_dict = {
        "HTTP_status_code": status_code,
        "message": msg,
        "error": True
    }
    resp_string = json.dumps(body_dict, sort_keys=True, indent=4)
    resp = make_response(resp_string, status_code)
    resp.mimetype = "application/json"
    abort(resp)


@app.after_request
def after_request_stuff(resp):
    #support CORS
    resp.headers['Access-Control-Allow-Origin'] = "*"
    resp.headers['Access-Control-Allow-Methods'] = "POST, GET, OPTIONS, PUT, DELETE, PATCH"
    resp.headers['Access-Control-Allow-Headers'] = "origin, content-type, accept, x-requested-with"

    # without this jason's heroku local buffers forever
    sys.stdout.flush()

    return resp






# ENDPOINTS
#
######################################################################################


@app.route('/', methods=["GET"])
@app.route('/v0', methods=["GET"])
@app.route('/v0/', methods=["GET"])
def index_endpoint():
    return jsonify({
        "version": "0.1",
        "name": "gtr-api",
        "description": "wrapper for GetTheResearch api",
        "msg": "Don't panic"
    })


@app.route("/paper/doi/<path:my_doi>", methods=["GET"])
def get_pub_by_doi(my_doi):
    my_clean_doi = clean_doi(my_doi)
    # print my_clean_doi
    my_doi_lookup = db.session.query(DoiLookup).filter(DoiLookup.doi==my_clean_doi).first()
    if not my_doi_lookup:
        abort_json(404, u"'{}' not found in db".format(my_clean_doi))

    query = db.session.query(Pub).filter(Pub.pmid==my_doi_lookup.pmid_numeric)
    # print query
    my_pub = query.first()
    # print my_pub
    if not my_pub:
        abort_json(404, u"'{}' is an invalid doi.  See https://doi.org/{}".format(my_clean_doi, my_clean_doi))

    my_pub_list = PubList(pubs=[my_pub])

    return jsonify({"results": my_pub_list.to_dict_serp_list()})


@app.route("/search/<path:query>", methods=["GET"])
def get_search_query(query):

    start_time = time()

    print "getting synonyms"
    synonym = get_synonym(query)
    print "getting terms from nerd"
    term_lookup = get_nerd_term_lookup(query)
    if synonym and not term_lookup:
        term_lookup = get_nerd_term_lookup(synonym)

    getting_term_lookup_elapsed = elapsed(start_time, 3)

    pmid_query_start_time = time()

    # page starts at 1 not 0
    if request.args.get("page"):
        page = int(request.args.get("page"))
    else:
        page = 1
    if page > 5:
        abort_json(400, u"Page too large. API currently only supports 5 pages right now, so page must be in the range 0-4.")

    if request.args.get("pagesize"):
        pagesize = int(request.args.get("pagesize"))
    else:
        pagesize = 10
    if pagesize > 100:
        abort_json(400, u"pagesize too large; max 100")

    oa_only = str_to_bool(request.args.get("oa", "false"))

    (my_pubs, time_to_pmids_elapsed, time_for_pubs_elapsed) = fulltext_search_title(query, synonym, oa_only)

    db_query_elapsed = elapsed(pmid_query_start_time, 3)

    initializing_publist_start_time = time()

    print "building response"
    sorted_pubs = sorted(my_pubs, key=lambda k: k.adjusted_score, reverse=True)

    my_pub_list = PubList(pubs=sorted_pubs[(pagesize * (page-1)):(pagesize * page)])

    initializing_publist_elapsed = elapsed(initializing_publist_start_time, 3)

    to_dict_start_time = time()

    results = my_pub_list.to_dict_serp_list(full=True)

    to_dict_elapsed = elapsed(to_dict_start_time, 3)
    total_time = elapsed(start_time, 3)

    print u"finished query for {}: took {} seconds".format(query, total_time)
    return jsonify({"results": results,
                    "page": page,
                    "synonym": synonym,
                    "term_lookup": term_lookup,
                    "timing": {"total": total_time,
                               "time_to_pmids_elapsed": time_to_pmids_elapsed,
                               "time_for_pubs_elapsed": time_for_pubs_elapsed,
                               "initializing_publist_elapsed": initializing_publist_elapsed,
                               "to_dict_elapsed": to_dict_elapsed,
                               "getting_term_lookup_elapsed": getting_term_lookup_elapsed
                               }
                    })


@app.route("/search/NEW/<path:query>", methods=["GET"])
def get_search_query_serp(query):

    start_time = time()

    print "getting synonyms"
    synonym = get_synonym(query)

    getting_synonym_lookup_elapsed = elapsed(start_time, 3)

    pmid_query_start_time = time()

    # page starts at 1 not 0
    if request.args.get("page"):
        page = int(request.args.get("page"))
    else:
        page = 1
    if page > 5:
        abort_json(400, u"Page too large. API currently only supports 5 pages right now, so page must be in the range 0-4.")

    if request.args.get("pagesize"):
        pagesize = int(request.args.get("pagesize"))
    else:
        pagesize = 10
    if pagesize > 100:
        abort_json(400, u"pagesize too large; max 100")

    oa_only = str_to_bool(request.args.get("oa", "false"))

    (my_pubs, time_to_pmids_elapsed, time_for_pubs_elapsed) = fulltext_search_title(query, synonym, oa_only)

    db_query_elapsed = elapsed(pmid_query_start_time, 3)
    initializing_publist_start_time = time()

    print "building response"
    # sorted_pubs = sorted(my_pubs, key=lambda k: k.adjusted_score, reverse=True)
    sorted_pubs = my_pubs
    chosen_pmid = [p.pmid for p in sorted_pubs[(pagesize * (page-1)):(pagesize * page)]]
    my_chosen_pubs = db.session.query(Pub).filter(Pub.pmid.in_(chosen_pmid)).options(orm.undefer_group('full')).all()
    my_pub_list = PubList(pubs=my_chosen_pubs)

    initializing_publist_elapsed = elapsed(initializing_publist_start_time, 3)
    to_dict_start_time = time()

    results = my_pub_list.to_dict_serp_list(full=False)

    to_dict_elapsed = elapsed(to_dict_start_time, 3)
    total_time = elapsed(start_time, 3)

    print u"finished query for {}: took {} seconds".format(query, total_time)
    return jsonify({"results": results,
                    "page": page,
                    "synonym": synonym,
                    "timing": {"total": total_time,
                               "time_to_pmids_elapsed": time_to_pmids_elapsed,
                               "time_for_pubs_elapsed": time_for_pubs_elapsed,
                               "initializing_publist_elapsed": initializing_publist_elapsed,
                               "to_dict_elapsed": to_dict_elapsed,
                               "getting_synonym_lookup_elapsed": getting_synonym_lookup_elapsed
                               }
                    })


# temporary hack to display all pictures
@app.route("/search/all_pictures", methods=["GET"])
def get_all_pictures_hack():

    # page starts at 1 not 0
    if request.args.get("page"):
        page = int(request.args.get("page"))
    else:
        page = 1

    if request.args.get("pagesize"):
        pagesize = int(request.args.get("pagesize"))
    else:
        pagesize = 10

    start_time = time()

    elapsed_time = 0

    all_results = []
    for image_uri in annotation_file_contents:
        image_dict = annotation_file_contents[image_uri]
        image_url = image_dict["orig_image_url"]
        if image_dict["alt_img"]:
            image_url = image_dict["alt_img"]
        n = image_dict["n"]
        annotation_title = image_dict["annotation_title"]
        if image_dict["bad_image_reason"]:
            image_url = ""
        img_label = ""
        if image_dict["bad_image_reason"]:
            img_label = u"EXCLUDED: {}".format(image_dict["bad_image_reason"])
        if image_dict["weight"]:
            img_label += u" weight={}".format(image_dict["weight"])
        all_results.append(
            {
            "abstract": "",
            "annotations": {},
            "author_lastnames": [],
            "best_host": "None",
            "best_version": "None",
            "doi": "42",
            "doi_url": "42",
            "image": {
                "abstract": "",
                "confidence": .42,
                "end": 0,
                "id": 42,
                "image_url": image_url,
                "label": img_label,
                "picture_score": 0.42,
                "raw_top_entity_score": 0.42,
                "spot": "",
                "start": 0,
                "title": img_label,
                "types": [],
                "uri": image_uri,
                "url": image_url
                },
            "is_oa": False,
            "journal_name": u"n = {}".format(n),
            "mesh": [],
            "num_paperbuzz_events": 0,
            "oa_url": None,
            "picture_candidates": [],
            "pmid": 42,
            "pmid_url": "",
            "pub_types": [],
            "score": 0,
            "abstract_short": None,
            "snippet": "",
            "title": annotation_title,
            "year": None,
            "n_in_annotation_sample": int(n)
            }
        )

    all_results = sorted(all_results, key=lambda x: x["n_in_annotation_sample"], reverse=True)
    results = all_results[(pagesize * (page-1)):(pagesize * page)]

    return jsonify({"results": results,
                    "page": page,
                    "pagesize": pagesize,
                    "synonym": None,
                    "term_lookup": None,
                    "elapsed_seconds": elapsed_time})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5011))
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)


















from flask import make_response
from flask import request
from flask import abort
from flask import render_template
from flask import jsonify

import json
import os
import logging
import sys
import requests
import re
import random
from time import time

from pub import Pub

from app import app
from app import db
from pub_list import PubList
from search import fulltext_search_title
from search import get_synonym
from search import get_nerd_term_lookup
from util import elapsed
from util import clean_doi
from util import get_sql_answers




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


# @app.route("/paper/doi/<path:my_doi>", methods=["GET"])
# def get_pub_by_doi(my_doi):
#     my_pub = db.session.query(Pub).filter(Pub.doi == my_doi).first()
#     if not my_pub:
#         abort_json(404, u"'{}' is an invalid doi.  See https://doi.org/{}".format(my_doi, my_doi))
#     return jsonify(my_pub.to_dict_full())

@app.route("/paper/pmid/<path:pmid>", methods=["GET"])
def get_pub_by_pmid(pmid):
    my_pmid = int(pmid)
    my_pub = db.session.query(Pub).filter(Pub.pmid == my_pmid).first()
    if not my_pub:
        abort_json(404, u"'{}' is an invalid pmid.  See https://pubmed.com/{}".format(my_pmid, my_pmid))
    return jsonify(my_pub.to_dict_full())


@app.route("/search/<path:query>", methods=["GET"])
def get_search_query(query):

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
        pagesize = 20
    if pagesize > 20:
        abort_json(400, u"pagesize too large; max 20")

    start_time = time()
    my_pubs = fulltext_search_title(query)

    print "building response"
    sorted_pubs = sorted(my_pubs, key=lambda k: k.adjusted_score, reverse=True)

    my_pub_list = PubList(pubs=sorted_pubs[(pagesize * (page-1)):(pagesize * page)])

    print "getting synonyms"
    synonym = get_synonym(query)
    print "getting terms from nerd"
    term_lookup = get_nerd_term_lookup(query)
    if synonym and not term_lookup:
        term_lookup = get_nerd_term_lookup(synonym)

    elapsed_time = elapsed(start_time, 3)
    print u"finished query for {}: took {} seconds".format(query, elapsed_time)
    return jsonify({"results": my_pub_list.to_dict_serp_list(),
                    "page": page,
                    "synonym": synonym,
                    "term_lookup": term_lookup,
                    "elapsed_seconds": elapsed_time})

# temporary hack to display all pictures
@app.route("/search/all_pictures", methods=["GET"])
def get_all_pictures_hack():
    print "hi heather!"

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
        pagesize = 20
    if pagesize > 20:
        abort_json(400, u"pagesize too large; max 20")

    start_time = time()

    # my_pubs = fulltext_search_title(query)
    #
    # print "building response"
    # sorted_pubs = sorted(my_pubs, key=lambda k: k.adjusted_score, reverse=True)
    #
    # my_pub_list = PubList(pubs=sorted_pubs[(pagesize * (page-1)):(pagesize * page)])
    #
    # print "getting synonyms"
    # synonym = get_synonym(query)
    # print "getting terms from nerd"
    # term_lookup = get_nerd_term_lookup(query)
    # if synonym and not term_lookup:
    #     term_lookup = get_nerd_term_lookup(synonym)

    elapsed_time = 0

    image_url = "https://upload.wikimedia.org/wikipedia/commons/4/4a/Impactstory-logo-2014.png"
    image_uri = "http://en.wikipedia.org/wiki/Extinction"
    n = 42
    annotation_title = "Impactstory logo"

    results = [
            {
            "abstract": "",
            "annotations": {},
            "author_lastnames": [],
            "best_host": "None",
            "best_version": "None",
            "date_of_electronic_publication": "",
            "doi": "42",
            "doi_url": "42",
            "image": {
            "abstract": "",
            "confidence": .42,
            "end": 0,
            "id": 42,
            "image_url": image_url,
            "label": "",
            "picture_score": 0.42,
            "raw_top_entity_score": 0.42,
            "spot": "",
            "start": 0,
            "title": "",
            "types": [],
            "uri": image_uri,
            "url": image_url
            },
            "is_oa": True,
            "journal_name": u"n = {}".format(n),
            "mesh": [],
            "num_paperbuzz_events": 0,
            "oa_url": None,
            "picture_candidates": [],
            "pmid": 42,
            "pmid_url": "",
            "pub_types": [],
            "score": 0,
            "short_abstract": None,
            "snippet": "",
            "title": annotation_title,
            "year": None
            }
    ]

    return jsonify({"results": results,
                    "page": page,
                    "synonym": None,
                    "term_lookup": None,
                    "elapsed_seconds": elapsed_time})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5011))
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)


















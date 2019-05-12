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
from search import autcomplete_entity_titles
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

    return jsonify({"results": my_pub_list.to_dict_serp_list(),
                    "annotations": my_pub_list.to_dict_annotation_metadata(),
                    })


@app.route("/search/<path:query>", methods=["GET"])
def get_search_query(query):

    attributes_to_hide = request.args.get("hide", "")

    start_time = time()
    entity = get_synonym(query)
    getting_entity_lookup_elapsed = elapsed(start_time, 3)

    # page starts at 1 not 0
    page = 1
    try:
        page = int(request.args.get("page"))
    except:
        pass

    if page > 10:
        abort_json(400, u"Page too large. API currently only supports 10 pages right now.")

    if request.args.get("pagesize"):
        pagesize = int(request.args.get("pagesize"))
    else:
        pagesize = 10
    if pagesize > 100:
        abort_json(400, u"pagesize too large; max 100")

    try:
        oa_only = str_to_bool(request.args.get("oa", "false"))
    except:
        oa_only = False

    (my_pubs, time_to_pmids_elapsed, time_for_pubs_elapsed) = fulltext_search_title(query, entity, oa_only)

    initializing_publist_start_time = time()
    sorted_pubs = sorted(my_pubs, key=lambda k: k.adjusted_score, reverse=True)
    my_pub_list = PubList(pubs=sorted_pubs[(pagesize * (page-1)):(pagesize * page)])
    initializing_publist_elapsed = elapsed(initializing_publist_start_time, 3)

    to_dict_start_time = time()
    full = "abstracts" not in attributes_to_hide
    results = my_pub_list.to_dict_serp_list(full=full)
    to_dict_elapsed = elapsed(to_dict_start_time, 3)

    response = {"results": results,
                    "page": page,
                    "oa_only": oa_only,
                    "query_entity": entity
                    }
    if not "annotations" in attributes_to_hide:
        response["annotations"] = my_pub_list.to_dict_annotation_metadata()

    jsonify_start_time = time()
    total_time = elapsed(start_time, 3)

    response["_timing"] = {"total": total_time,
                           "time_to_pmids_elapsed": time_to_pmids_elapsed,
                           "time_for_pubs_elapsed": time_for_pubs_elapsed,
                           "initializing_publist_elapsed": initializing_publist_elapsed,
                           "to_dict_elapsed": to_dict_elapsed,
                           "getting_entity_lookup_elapsed": getting_entity_lookup_elapsed
                        }
    jsonified_response = jsonify(response)
    jsonify_elapsed = elapsed(jsonify_start_time)
    print u"jsonify_elapsed took {} seconds".format(jsonify_elapsed)
    print u"finished query for {}: took {} seconds".format(query, elapsed(start_time))
    return jsonified_response


@app.route("/autocomplete/<query>", methods=["GET"])
def get_autocomplete_entity_titles(query):

    start_time = time()

    results = autcomplete_entity_titles(query)

    total_time = elapsed(start_time)

    timings = [
       ("TOTAL", total_time)
       ]

    return jsonify({"results": results,
                    "_timing": [u"{:>30}: {}".format(a, b) for (a, b) in timings]
                    })




# things to try
# don't return annotations to start with
# don't return full abstracts to start with
# only return 3 things
# fewer than 100 articles to sort
# maybe new indices etc?
# just the count of the length of the abstract etc

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5011))
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)


















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
from annotation import annotation_file_contents
from search import autocomplete_entity_titles
from search import get_cached_api_response
from query_stopwords import get_entities_from_query
from notifications import notification_signup
from history import log_query
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

    query = db.session.query(Pub).filter(Pub.pmid==my_doi_lookup.pmid).options(orm.undefer_group('full'))
    # print query
    my_pub = query.first()
    # print my_pub
    if not my_pub:
        abort_json(404, u"'{}' is an invalid doi.  See https://doi.org/{}".format(my_clean_doi, my_clean_doi))

    my_pub_list = PubList(pubs=[my_pub])
    my_pub_list.set_dandelions()
    my_pub_list.set_pictures()
    results = my_pub_list.to_dict_serp_list()
    return jsonify({"results": my_pub_list.to_dict_serp_list(),
                    "annotations": my_pub_list.to_dict_annotation_metadata(),
                    })

@app.route("/paper/pmid/<path:my_pmid>", methods=["GET"])
def get_pub_by_pmid(my_pmid):
    query = db.session.query(Pub).filter(Pub.pmid==int(my_pmid)).options(orm.undefer_group('full'))
    # print query
    my_pub = query.first()
    # print my_pub
    if not my_pub:
        abort_json(404, u"'{}' is not a pmid in our database")

    my_pub_list = PubList(pubs=[my_pub])
    my_pub_list.set_dandelions()
    my_pub_list.set_pictures()
    results = my_pub_list.to_dict_serp_list()
    return jsonify({"results": results,
                    "annotations": my_pub_list.to_dict_annotation_metadata(),
                    })


@app.route("/search/<path:query>", methods=["GET"])
def get_search_query(query):

    start_time = time()

    query = query.replace(u"_", u" ")
    if request.headers.getlist("X-Forwarded-For"):
        ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        ip = request.remote_addr

    log_query(query, ip)

    no_live_calls = request.args.get("no-live-calls", "")
    return_full_api_response = True
    if request.args.get("minimum", ""):
        return_full_api_response = False

    query_entities = get_entities_from_query(query)
    print "query_entities", query_entities
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

    if query_entities and len(query_entities)==1 and page==1:
        cached_response = get_cached_api_response(query_entities[0], oa_only)
        if cached_response and cached_response[0]:
            cached_response = cached_response[0]
            total_time = elapsed(start_time, 3)
            cached_response["_from_cache"] = True
            cached_response["_timing"] = {"total": total_time}
            print "got response!!!"
            return jsonify(cached_response)

    (pubs_to_sort, time_to_pmids_elapsed, time_for_pubs_elapsed) = fulltext_search_title(query, query_entities, oa_only, full=return_full_api_response)

    initializing_publist_start_time = time()
    # sorted_pubs = sorted(pubs_to_sort, key=lambda k: k.adjusted_score, reverse=True)
    # selected_pubs = sorted_pubs[(pagesize * (page-1)):(pagesize * page)]
    # selected_pmids = [p.pmid for p in selected_pubs]

    sorted_pubs = sorted(pubs_to_sort, key=lambda k: k["adjusted_score"], reverse=True)
    selected_pubs = sorted_pubs[(pagesize * (page-1)):(pagesize * page)]
    selected_pmids = [p["pmid"] for p in selected_pubs]

    selected_pubs_full = db.session.query(Pub).filter(Pub.pmid.in_(selected_pmids)).options(orm.undefer_group('full')).all()
    selected_pubs_full = [p for p in selected_pubs_full if not p.suppress]  # get rid of retracted ones

    my_pub_list = PubList(pubs=selected_pubs_full)
    initializing_publist_elapsed = elapsed(initializing_publist_start_time, 3)

    set_dandelions_start_time = time()
    if not no_live_calls:
        my_pub_list.set_dandelions()
    set_dandelions_elapsed = elapsed(set_dandelions_start_time)
    set_pictures_start_time = time()
    my_pub_list.set_pictures()
    set_pictures_elapsed = elapsed(set_pictures_start_time)

    to_dict_start_time = time()
    results = my_pub_list.to_dict_serp_list(full=return_full_api_response)


    response = {"results": results,
                    "page": page,
                    "oa_only": oa_only,
                    "total_num_pubs": len(pubs_to_sort),
                    "query_entities": query_entities
                    }
    if return_full_api_response:
        response["annotations"] = my_pub_list.to_dict_annotation_metadata()

    to_dict_elapsed = elapsed(to_dict_start_time, 3)
    total_time = elapsed(start_time, 3)

    response["_timing"] = {"9 total": total_time,
                           "1 getting_entity_lookup_elapsed": getting_entity_lookup_elapsed,
                           "2 time_to_pmids_elapsed": time_to_pmids_elapsed,
                           "3 time_for_pubs_elapsed": time_for_pubs_elapsed,
                           "4 initializing_publist_elapsed": initializing_publist_elapsed,
                           "5 set_dandelions_elapsed": set_dandelions_elapsed,
                           "6 set_pictures_elapsed": set_pictures_elapsed,
                           "7 to_dict_elapsed": to_dict_elapsed,
                        }

    print u"finished query for {}: took {} seconds".format(query, elapsed(start_time))
    return jsonify(response)


@app.route("/autocomplete/<query>", methods=["GET"])
def get_autocomplete_entity_titles(query):

    start_time = time()

    # results = [a for a in entities_for_autocomplete if a.lower().startswith(query.lower())][0:8]
    results = autocomplete_entity_titles(query)

    total_time = elapsed(start_time, 4)

    return jsonify({"results": results,
                    "_timing": {"total": total_time}
                    })


# to test
# curl -H "Content-Type: application/json" --data '{"email":"hpiwowar@gmail.com","query":"frogs"}'  http://localhost:5000/notifications/signup


@app.route("/notifications/signup", methods=["POST"])
def notifications_signup_post():
    post_data = request.get_json()
    if not post_data or "email" not in post_data or "query" not in post_data:
        abort_json(422, "missing arguments")
    print u"signing {} up for alerts for >>>{}<<<".format(post_data["email"], post_data["query"])

    notification_signup(post_data["email"], post_data["query"])

    return jsonify({"response": "success", "email": post_data["email"], "query": post_data["query"]})



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


















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
from search import fulltext_search_title
from search import autocomplete_phrases
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


@app.route("/doi/<path:doi>", methods=["GET"])
def get_pub_by_doi(doi):
    my_doi = clean_doi(doi)
    my_pub = db.session.query(Pub).filter(Pub.doi_url == u"https://doi.org/{}".format(my_doi)).first()
    if not my_pub:
        abort_json(404, u"'{}' is an invalid doi.  See https://doi.org/{}".format(my_doi, my_doi))
    return jsonify(my_pub.to_dict_full())

@app.route("/pmid/<path:pmid>", methods=["GET"])
def get_pub_by_pmid(pmid):
    my_pmid = pmid
    my_pub = db.session.query(Pub).filter(Pub.pmid == my_pmid).first()
    if not my_pub:
        abort_json(404, u"'{}' is an invalid pmid.  See https://pubmed.com/{}".format(my_pmid, my_pmid))
    return jsonify(my_pub.to_dict_full())


@app.route("/search/<path:query>", methods=["GET"])
def get_search_query(query):
    start_time = time()
    my_pubs = fulltext_search_title(query)

    response = [my_pub.to_dict_serp() for my_pub in my_pubs]
    sorted_response = sorted(response, key=lambda k: k['score'], reverse=True)

    elapsed_time = elapsed(start_time, 3)
    return jsonify({"results": sorted_response, "elapsed_seconds": elapsed_time})

@app.route("/search/autocomplete/<path:query>", methods=["GET"])
def get_search_autocomplete_query(query):
    start_time = time()
    response = autocomplete_phrases(query)
    sorted_response = sorted(response, key=lambda k: k['score'], reverse=True)
    elapsed_time = elapsed(start_time, 3)
    return jsonify({"results": sorted_response, "elapsed_seconds": elapsed_time})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5011))
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)


















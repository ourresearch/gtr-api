from multiprocessing.pool import ThreadPool
import requests
import argparse
import os
from time import time
from time import sleep
import datetime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import sql
from sqlalchemy import orm
from sqlalchemy import or_
import json
from sqlalchemy.orm.attributes import flag_modified

from app import db
from pub import call_dandelion
from pub import Pub
from pub import Dandelion
from util import elapsed
from util import safe_commit
from util import TooManyRequestsException
from entity import stop_words
from search import CachedEntityResponse
from views import get_search_query

def cache_api_response(my_saved_object):
    entity_term  = my_saved_object.entity_title
    entity_term = entity_term.replace(u" ", u"_")

    url = u"https://gtr-api.herokuapp.com/search/{}?automated=true&nocache=true".format(entity_term)
    r = requests.get(url)
    print r
    print url
    my_saved_object.api_response = r.json()
    flag_modified(my_saved_object, "api_response")  # required, to force sqlalchemy to update because jsonb

    url = u"https://gtr-api.herokuapp.com/search/{}?oa=true&automated=true&nocache=true".format(entity_term)
    r = requests.get(url)
    print r
    print url
    my_saved_object.api_response_oa_only = r.json()
    flag_modified(my_saved_object, "api_response_oa_only")  # required, to force sqlalchemy to update because jsonb

    my_saved_object.collected = datetime.datetime.utcnow()
    db.session.merge(my_saved_object)
    safe_commit(db)
    print ".",

    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run stuff.")
    parser.add_argument('--since', nargs="?", type=str, default=False, help="date since to dirty cache")
    parser.add_argument('--entity', nargs="?", type=str, default=False, help="entity to refresh")
    parsed_args = parser.parse_args()
    parsed_vars = vars(parsed_args)

    start = time()

    before_date = datetime.datetime.utcnow()

    if __name__ == '__main__':
        something_to_do = True
        while something_to_do:
            # query = u"""select * from search_autocomplete_dandelion_mv
            #     where entity_title not in (select entity_title from cached_entity_response)
            #     order by sum_num_events desc
            #     limit 25
            #     """
            # rows = db.engine.execute(sql.text(query)).fetchall()
            # query = u"""select * from cached_entity_response
            #     where created < :collected :: timestamp
            #     order by created desc
            #     limit 25
            #     """
            # rows = db.engine.execute(sql.text(query), collected=collected).fetchall()
            # entity_titles = [row[0] for row in rows]
            # for entity_title in entity_titles:
            #     my_saved_object = CachedEntityResponse.get(entity_title)
            #     if not my_saved_object:
            #         print u"object not found, creating"
            #         my_saved_object = CachedEntityResponse(entity_title=entity_title)
            #         db.session.add(my_saved_object)
            #     my_saved_objects.append(my_saved_object)


            before_date = parsed_vars.get("before", None)
            debug = parsed_vars.get("debug", None)
            single_entity_title = parsed_vars.get("entity", None)
            # single_entity_title =  'Gluten-free diet'

            my_saved_objects = []
            if single_entity_title:
                my_saved_objects = CachedEntityResponse.query.filter(CachedEntityResponse.entity_title.ilike(single_entity_title)).\
                    order_by(CachedEntityResponse.collected.asc()).limit(25).all()
                something_to_do = False  # only do this once

            elif before_date:
                my_saved_objects = CachedEntityResponse.query.\
                    filter(or_(CachedEntityResponse.collected==None, CachedEntityResponse.collected < before_date)).\
                    order_by(CachedEntityResponse.collected.asc()).limit(25).all()

            if my_saved_objects:
                use_threads = not debug  # useful to turn off pooling to help debugging
                if use_threads:
                    my_thread_pool = ThreadPool(20)
                    results = my_thread_pool.imap_unordered(cache_api_response, my_saved_objects)
                    my_thread_pool.close()
                    my_thread_pool.join()
                    my_thread_pool.terminate()
                else:
                    for my_saved_object in my_saved_objects:
                        cache_api_response(my_saved_object)
            else:
                print "nothing to do"
                something_to_do = False

            db.session.remove()
            # print "finished update in {}sec".format(elapsed(start))
            print "*",


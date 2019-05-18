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
import json
from sqlalchemy.orm.attributes import flag_modified

from app import db
from pub import call_dandelion
from pub import Pub
from pub import Dandelion
from util import elapsed
from util import safe_commit
from util import TooManyRequestsException
from query_stopwords import stop_words
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
    parser.add_argument('--since', nargs="?", type=str, default=False, help="just add twitter")
    parsed = parser.parse_args()

    start = time()

    before_date = datetime.datetime.utcnow()

    if __name__ == '__main__':
        while True:
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


            single_entity_title = None
            # single_entity_title =  'Gluten-free diet'
            if single_entity_title:
                my_saved_objects = CachedEntityResponse.query.filter(CachedEntityResponse.entity_title == single_entity_title).\
                    order_by(CachedEntityResponse.collected.asc()).limit(25).all()
            else:
                my_saved_objects = CachedEntityResponse.query.filter(CachedEntityResponse.collected < before_date).\
                    order_by(CachedEntityResponse.collected.asc()).limit(25).all()

            use_threads = True  # useful to turn off pooling to help debugging
            my_thread_pool = ThreadPool(20)
            if use_threads:
                results = my_thread_pool.imap_unordered(cache_api_response, my_saved_objects)
                my_thread_pool.close()
                my_thread_pool.join()
            else:
                for my_saved_object in my_saved_objects:
                    cache_api_response(my_saved_object)

            my_thread_pool.terminate()

            # print results

            db.session.remove()
            # print "finished update in {}sec".format(elapsed(start))
            print "*",


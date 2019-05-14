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
    url = "https://gtr-api.herokuapp.com/search/{}".format(my_saved_object.entity_title)
    r = requests.get(url)
    print r
    print url
    my_saved_object.api_response = r.json()

    url = "https://gtr-api.herokuapp.com/search/{}?oa=true".format(my_saved_object.entity_title)
    r = requests.get(url)
    print r
    print url
    my_saved_object.api_response_oa_only = r.json()

    my_saved_object.collected = datetime.datetime.utcnow()
    db.session.merge(my_saved_object)
    safe_commit(db)
    print ".",

    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run stuff.")
    # parser.add_argument('--just_add_twitter', nargs="?", type=bool, default=False, help="just add twitter")
    parsed = parser.parse_args()

    start = time()

    if __name__ == '__main__':
        while True:
            query = """select * from search_autocomplete_dandelion_mv 
                where entity_title not in (select entity_title from cached_entity_response) 
                order by sum_num_events desc 
                limit 25
                """
            rows = db.engine.execute(sql.text(query)).fetchall()
            entity_titles = [row[0] for row in rows]

            my_saved_objects = []
            for entity_title in entity_titles:
                my_saved_object = CachedEntityResponse(entity_title=entity_title)
                db.session.add(my_saved_object)
                my_saved_objects.append(my_saved_object)

            use_threads = False  # useful to turn off pooling to help debugging
            my_thread_pool = ThreadPool(5)
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


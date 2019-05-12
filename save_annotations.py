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


def call_dandelion_on_article(my_queue_save_obj):
    dandelion_results = None
    error = None
    rate_limit_exceeded = False
    batch_api_key = os.getenv("DANDELION_API_KEYS_FOR_BATCH")

    if not my_queue_save_obj:
        error = "no my_queue_save_obj"
        print "x",

    if not hasattr(my_queue_save_obj, "my_pub") or not my_queue_save_obj.my_pub:
        # print u"no pub for {}, returning".format(my_queue_save_obj.pmid)
        error = "no pub object"
        print "n",
    else:
        print "y",

    if not rate_limit_exceeded:
        try:
            if not rate_limit_exceeded and my_queue_save_obj.my_pub:
                my_text = my_queue_save_obj.my_pub.article_title
                dandelion_results = call_dandelion(my_text, batch_api_key)
                my_queue_save_obj.dandelion_raw_article_title = dandelion_results

            if not rate_limit_exceeded and my_queue_save_obj.my_pub:
                my_text = my_queue_save_obj.my_pub.abstract_text
                dandelion_results = call_dandelion(my_text, batch_api_key)
                my_queue_save_obj.dandelion_raw_abstract_text = json.dumps(dandelion_results) # this one is a string for some reason

        except TooManyRequestsException:
            print "!",
            error = u"TooManyRequestsException"
            rate_limit_exceeded = True

    if not rate_limit_exceeded:
        my_queue_save_obj.dandelion_collected = datetime.datetime.utcnow()
        try:
            db.session.merge(my_queue_save_obj)
            safe_commit(db)
        except Exception, e:
            print e
        print ".",
    return (dandelion_results, error, rate_limit_exceeded)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run stuff.")

    # just for updating lots
    # parser.add_argument('file_name', type=str, help="filename to import")
    # parser.add_argument('campaign', type=str, help="name of campaign")
    # parser.add_argument('--limit', "-l", nargs="?", type=int, help="how many lines to import")
    # parser.add_argument('--just_add_twitter', nargs="?", type=bool, default=False, help="just add twitter")
    parsed = parser.parse_args()

    start = time()

    if __name__ == '__main__':
        for i in range(100000):
            query = Dandelion.query.filter(Dandelion.dandelion_collected == None,
                                           Dandelion.num_events != None,
                                           Dandelion.pmid != None).\
                order_by(Dandelion.num_events.desc())\
                .limit(15)  # max 50/3, doing 3 calls for each DOI and can hit dandelion w 50 at a time
            queue_save_objs = query.all()
            pmids = [save_obj.pmid for save_obj in queue_save_objs]
            my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).options(orm.noload('*')).all()
            for save_obj in queue_save_objs:
                matches = [my_pub for my_pub in my_pubs if my_pub.pmid==save_obj.pmid]
                if matches:
                    save_obj.my_pub = matches[0]
                else:
                    save_obj.my_pub = None

            use_threads = True  # useful to turn off pooling to help debugging
            my_thread_pool = ThreadPool(50)
            if use_threads:
                results = my_thread_pool.imap_unordered(call_dandelion_on_article, queue_save_objs)
                my_thread_pool.close()
                my_thread_pool.join()
            else:
                results = []
                for my_obj in queue_save_objs:
                    results.append(call_dandelion_on_article(my_obj))

            try:
                for (my_result, my_error, rate_limit_exceeded) in results:
                    if rate_limit_exceeded:
                        print "sleeping for a few minutes because rate_limit_exceeded", my_error
                        sleep(60*5)
            except Exception as e:
                print e
                print "sleeping for a minute"
                sleep(60)

            my_thread_pool.terminate()

            # print results

            db.session.remove()
            # print "finished update in {}sec".format(elapsed(start))
            print "*",


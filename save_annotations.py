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
from pub import PubDoi
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

    if not error and not rate_limit_exceeded:
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
        while True:
            query = u"""select ricks_gtr_sort_results.doi, pmid, num_events from ricks_gtr_sort_results 
                where ricks_gtr_sort_results.doi not in (select doi from dandelion_by_doi) 
                and num_events is not null 
                and num_events >= 25
                and doi is not null
                limit 25 
                """
            rows = db.engine.execute(sql.text(query)).fetchall()
            lookup = {}
            if rows:
                dois = [row[0] for row in rows]
                for row in rows:
                    lookup[row[0]] = {"doi": row[0], "num_events": int(row[2]), "used": False}
            else:
                print "no rows without dandelions, so sleeping"
                sleep(60*60)

            # print pmids
            my_pubs = db.session.query(PubDoi).filter(PubDoi.doi.in_(dois)).options(orm.noload('*')).all()
            my_dandelions = []
            for my_pub in my_pubs:
                my_dandelion = Dandelion(doi=my_pub.doi)
                my_dandelion.doi = lookup[my_pub.doi]["doi"]
                my_dandelion.num_events = lookup[my_pub.doi]["num_events"]
                lookup[my_pub.doi]["used"] = True
                my_dandelion.my_pub = my_pub
                db.session.add(my_dandelion)
                my_dandelions.append(my_dandelion)
            for (doi, my_dict) in lookup.iteritems():
                if not my_dict["used"]:
                    print "#",
                    my_dandelion = Dandelion(doi=doi)
                    my_dandelion.doi = my_dict["doi"]
                    my_dandelion.num_events = my_dict["num_events"]
                    db.session.add(my_dandelion)
                    # but don't append it; it doesn't need to get run

            safe_commit(db)

            print "now calling dandelion"

            try:
                my_thread_pool = ThreadPool(50)
                results = my_thread_pool.imap_unordered(call_dandelion_on_article, my_dandelions)
                my_thread_pool.close()
                my_thread_pool.join()
                my_thread_pool.terminate()

            except AttributeError:
                results = []
                for my_dandelion in my_dandelions:
                    results.append(call_dandelion_on_article(my_dandelion))

            try:
                for (my_result, my_error, rate_limit_exceeded) in results:
                    if rate_limit_exceeded:
                        print "sleeping for a few minutes because rate_limit_exceeded", my_error
                        sleep(60*5)
            except Exception as e:
                print e
                print "sleeping for a minute"
                sleep(60)

            # print results

            db.session.remove()
            # print "finished update in {}sec".format(elapsed(start))
            print "*",


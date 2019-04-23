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

from app import db
from pub import call_dandelion
from pub import Pub
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
        print "X",

    if not error:
        for annotation_type in ["article_title", "abstract_short", "abstract_text"]:

            try:
                my_text = getattr(my_queue_save_obj.my_pub, annotation_type)
                dandelion_results = call_dandelion(my_text, batch_api_key)
                setattr(my_queue_save_obj, u"dandelion_raw_{}".format(annotation_type), dandelion_results)

                # print "\n"
                # print my_queue_save_obj.article_title

                if dandelion_results:
                    for annotation_dict in dandelion_results.get("annotations", []):
                        my_annotation = AnnotationSave(annotation_dict)
                        my_annotation.doi = my_queue_save_obj.doi
                        my_annotation.annotation_type = annotation_type

                        for top_entity in dandelion_results.get("topEntities", []):
                            if my_annotation.uri == top_entity["uri"]:
                                my_annotation.top_entity_score = top_entity["score"]

                        # print my_annotation
                        db.session.merge(my_annotation)

            except TooManyRequestsException:
                print "x",
                error = u"TooManyRequestsException"
                rate_limit_exceeded = True

    my_queue_save_obj.dandelion_collected = datetime.datetime.utcnow()
    db.session.merge(my_queue_save_obj)
    safe_commit(db)
    print ".",
    return (dandelion_results, error, rate_limit_exceeded)


class QueueSave(db.Model):
    __tablename__ = "dois_paperbuzz_dandelion"
    doi = db.Column(db.Text, primary_key=True)
    pmid = db.Column(db.Numeric)
    num_events = db.Column(db.Numeric)
    dandelion_raw_article_title = db.Column(JSONB)
    dandelion_raw_abstract_short = db.Column(JSONB)
    dandelion_raw_abstract_text = db.Column(JSONB)
    dandelion_collected = db.Column(db.DateTime)

    def __repr__(self):
        return u'<QueueSave ({doi}) {num_events}>'.format(
            doi=self.doi,
            num_events=self.num_events
        )

class AnnotationSave(db.Model):
    __tablename__ = "doi_annotations"
    doi = db.Column(db.Text, primary_key=True)
    annotation_type = db.Column(db.Text, primary_key=True)
    spot = db.Column(db.Text)
    title = db.Column(db.Text)
    uri = db.Column(db.Text, primary_key=True)
    image = db.Column(db.Text)
    top_entity_score = db.Column(db.Text)
    confidence = db.Column(db.Text)

    def __init__(self, dandelion_raw_annotation):
        self.spot = dandelion_raw_annotation.get("spot", None)
        self.title = dandelion_raw_annotation.get("title", None)
        self.uri = dandelion_raw_annotation.get("uri", None)
        self.confidence = dandelion_raw_annotation.get("confidence", None)
        if "image" in dandelion_raw_annotation and dandelion_raw_annotation["image"]:
            self.image = dandelion_raw_annotation["image"]["full"]

    def __repr__(self):
        return u'<AnnotationSave ({doi}) {uri} {top_entity_score}>'.format(
            doi=self.doi,
            uri=self.uri,
            top_entity_score=self.top_entity_score
        )


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
            query = QueueSave.query.filter(QueueSave.dandelion_collected == None,
                                           QueueSave.num_events != None,
                                           QueueSave.pmid != None).\
                order_by(QueueSave.num_events.desc())\
                .limit(15)  # max 50/3, doing 3 calls for each DOI and can hit dandelion w 50 at a time
            queue_save_objs = query.all()
            pmids = [int(save_obj.pmid) for save_obj in queue_save_objs]
            # print pmids
            my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).options(orm.noload('*')).all()
            # print my_pubs
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
                        print "sleeping because rate_limit_exceeded", my_error
                        sleep(60*60)
            except Exception as e:
                print e
                print "sleeping for a minute"
                sleep(60)

            my_thread_pool.terminate()

            # print results

            db.session.remove()
            # print "finished update in {}sec".format(elapsed(start))
            print "*",


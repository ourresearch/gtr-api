from multiprocessing.pool import ThreadPool
import requests
import argparse
import os
from time import time
import datetime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import sql

from app import db
from pub import call_dandelion
from util import elapsed
from util import safe_commit

def call_dandelion_on_article_title(my_queue_save_obj):
    dandelion_results = call_dandelion(my_queue_save_obj.article_title)
    my_queue_save_obj.dandelion_raw = dandelion_results
    my_queue_save_obj.dandelion_collected = datetime.datetime.utcnow()

    list_of_annotation_objects = []
    # print "\n"
    # print my_queue_save_obj.article_title

    for annotation_dict in dandelion_results["annotations"]:
        my_annotation = AnnotationSave(annotation_dict)
        my_annotation.doi = my_queue_save_obj.doi
        my_annotation.article_title = my_queue_save_obj.article_title

        for top_entity in dandelion_results.get("topEntities", []):
            if my_annotation.uri == top_entity["uri"]:
                my_annotation.top_entity_score = top_entity["score"]

        # print my_annotation
        db.session.merge(my_annotation)

    db.session.merge(my_queue_save_obj)
    safe_commit(db)
    print ".",
    return dandelion_results


class QueueSave(db.Model):
    __tablename__ = "dois_paperbuzz_dandelion"
    doi = db.Column(db.Text, primary_key=True)
    pmid = db.Column(db.Numeric)
    num_events = db.Column(db.Numeric)
    article_title = db.Column(db.Text)
    dandelion_raw = db.Column(JSONB)
    dandelion_collected = db.Column(db.DateTime)

    def __repr__(self):
        return u'<QueueSave ({doi}) {article_title}>'.format(
            doi=self.doi,
            article_title=self.article_title
        )

class AnnotationSave(db.Model):
    __tablename__ = "doi_annotations"
    doi = db.Column(db.Text, primary_key=True)
    article_title = db.Column(db.Text)
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
            query = QueueSave.query.filter(QueueSave.dandelion_collected==None).\
                            filter(QueueSave.article_title!=None).\
                            order_by(QueueSave.num_events.desc()).limit(45)
            objs = query.all()

            my_thread_pool = ThreadPool(25)
            results = my_thread_pool.imap_unordered(call_dandelion_on_article_title, objs)
            my_thread_pool.close()
            my_thread_pool.join()
            # for result in results:
                # if error:
                #     print "error fetching", pmid, error
            my_thread_pool.terminate()

            # print results

            db.session.remove()
            # print "finished update in {}sec".format(elapsed(start))
            print "*",


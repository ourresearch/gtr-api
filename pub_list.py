from multiprocessing.pool import ThreadPool
from time import time as timer
import requests

from annotation_list import AnnotationList

image_blacklist = [
    "Prospective_cohort_study",
    "Patient",
    "Randomized_controlled_trial",
    "Scientific_method",
    "Therapy",
    "Health",
    "Statistical_population",
    "Clinical_trial",
    "Risk",
    "Meta-analysis",
    "Systematic_review",
    "Human_sexual_activity",
    "Adult"
    ]

def call_dandelion_on_article_title(pub):
    try:
        response_data = pub.call_dandelion_on_article_title()
        return (response_data, pub.pmid, None)
    except Exception as e:
        return (None, pub.pmid, e)

def call_dandelion_on_abstract(pub):
    try:
        response_data = pub.call_dandelion_on_abstract()
        return (response_data, pub.pmid, None)
    except Exception as e:
        return (None, pub.pmid, e)

def call_dandelion_on_short_abstract(pub):
    try:
        response_data = pub.call_dandelion_on_short_abstract()
        return (response_data, pub.pmid, None)
    except Exception as e:
        return (None, pub.pmid, e)

class PubList(object):

    def __init__(self, pubs):
        self.pubs = pubs

    def set_dandelions(self):
        start = timer()
        my_thread_pool = ThreadPool(25)

        results = my_thread_pool.imap(call_dandelion_on_article_title, self.pubs)
        for result, pmid, error in results:
            if error:
                print "error fetching", pmid, error

        results = my_thread_pool.imap(call_dandelion_on_abstract, self.pubs)
        for result, pmid, error in results:
            if error:
                print "error fetching", pmid, error

        results = my_thread_pool.imap(call_dandelion_on_short_abstract, self.pubs)
        for result, pmid, error in results:
            if error:
                print "error fetching", pmid, error

        print("Elapsed Time: %s" % (timer() - start,))
        my_thread_pool.terminate()

    def set_annotations_and_pictures(self):
        self.set_dandelions()
        chosen_images = set()

        for my_pub in self.pubs:
            reverse_sorted_picture_candidates = sorted(my_pub.dandelion_title_annotation_list.list(), key=lambda x: x.picture_score, reverse=False)
            my_pub.picture_candidates = reverse_sorted_picture_candidates
            my_pub.image = None

            for candidate in my_pub.picture_candidates:
                if candidate not in chosen_images:
                    my_pub.image = candidate

            if my_pub.image:
                chosen_images.add(my_pub.image)


    def to_dict_serp_list(self):

        self.set_annotations_and_pictures()

        response = []
        for my_pub in self.pubs:
            pub_dict = my_pub.to_dict_serp()
            pub_dict["picture_candidates"] = [a.to_dict_simple() for a in reversed(my_pub.picture_candidates)]
            pub_dict["image"] = my_pub.image.to_dict_simple()
            pub_dict["annotations"] = {"using_article_abstract": None, "using_article_short_abstract": None, "using_article_title": None}
            if hasattr(my_pub, "dandelion_abstract_annotation_list") and my_pub.dandelion_abstract_annotation_list:
                pub_dict["annotations"]["using_article_abstract"] = my_pub.dandelion_abstract_annotation_list.to_dict_simple()
            if hasattr(my_pub, "dandelion_short_abstract_annotation_list") and my_pub.dandelion_short_abstract_annotation_list:
                pub_dict["annotations"]["using_article_short_abstract"] = my_pub.dandelion_short_abstract_annotation_list.to_dict_simple()
            if hasattr(my_pub, "dandelion_title_annotation_list") and my_pub.dandelion_title_annotation_list:
                pub_dict["annotations"]["using_article_title"] = my_pub.dandelion_title_annotation_list.to_dict_simple()

            response.append(pub_dict)

        return response




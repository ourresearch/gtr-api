from multiprocessing.pool import ThreadPool
from time import time as timer
import requests
from collections import Counter
from collections import defaultdict

from annotation_list import AnnotationList

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
        results = my_thread_pool.imap_unordered(call_dandelion_on_article_title, self.pubs)
        my_thread_pool.close()
        my_thread_pool.join()
        for result, pmid, error in results:
            if error:
                print "error fetching", pmid, error
        my_thread_pool.terminate()

        my_thread_pool = ThreadPool(25)
        results = my_thread_pool.imap_unordered(call_dandelion_on_abstract, self.pubs)
        my_thread_pool.close()
        my_thread_pool.join()
        for result, pmid, error in results:
            if error:
                print "error fetching", pmid, error
        my_thread_pool.terminate()

        # my_thread_pool = ThreadPool(25)
        # results = my_thread_pool.imap_unordered(call_dandelion_on_short_abstract, self.pubs)
        # my_thread_pool.close()
        # my_thread_pool.join()
        # for result, pmid, error in results:
        #     if error:
        #         print "error fetching", pmid, error
        # my_thread_pool.terminate()

        print("elapsed time spent calling dandelion: %s" % (timer() - start,))

    def set_annotations_and_pictures(self):
        self.set_dandelions()
        chosen_image_urls = set()

        # get annotations distribution, so pubs can use this to boost rare mentions
        annotation_counter = Counter()
        for my_pub in self.pubs:
            for annotation in my_pub.annotations_for_pictures:
                if annotation.image_url:
                    annotation_counter[annotation.image_url] += 1
        annotation_counter_normalized = defaultdict(float)
        try:
            max_mentions = annotation_counter.most_common(1)[0][1] + 0.0
            for my_key in annotation_counter:
                annotation_counter_normalized[my_key] = annotation_counter[my_key] / max_mentions
        except:
            pass

        for my_pub in self.pubs:
            my_pub.set_annotation_distribution(annotation_counter_normalized)
            reverse_sorted_picture_candidates = sorted(my_pub.annotations_for_pictures, key=lambda x: x.picture_score, reverse=False)
            my_pub.picture_candidates = reverse_sorted_picture_candidates
            my_pub.image = None

            for candidate in my_pub.picture_candidates:
                # make sure is positive, otherwise blacklisted
                if candidate.picture_score >= 0:
                    if candidate.image_url not in chosen_image_urls:
                        my_pub.image = candidate

            if my_pub.image:
                chosen_image_urls.add(my_pub.image.image_url)


    def to_dict_serp_list(self, include_abstracts=True):

        self.set_annotations_and_pictures()

        response = []
        for my_pub in self.pubs:
            pub_dict = my_pub.to_dict_serp(include_abstracts)
            pub_dict["picture_candidates"] = [a.to_dict_simple() for a in reversed(my_pub.picture_candidates) if a]
            if my_pub.image:
                pub_dict["image"] = my_pub.image.to_dict_simple()
            else:
                pub_dict["image"] = {}
            pub_dict["annotations"] = {"using_article_abstract": None, "using_article_short_abstract": None, "using_article_title": None}
            if hasattr(my_pub, "dandelion_title_annotation_list") and my_pub.dandelion_title_annotation_list:
                pub_dict["annotations"]["using_article_title"] = my_pub.dandelion_title_annotation_list.to_dict_simple()

            if include_abstracts:
                if hasattr(my_pub, "dandelion_abstract_annotation_list") and my_pub.dandelion_abstract_annotation_list:
                    pub_dict["annotations"]["using_article_abstract"] = my_pub.dandelion_abstract_annotation_list.to_dict_simple()
                # if hasattr(my_pub, "dandelion_short_abstract_annotation_list") and my_pub.dandelion_short_abstract_annotation_list:
                #     pub_dict["annotations"]["using_article_short_abstract"] = my_pub.dandelion_short_abstract_annotation_list.to_dict_simple()

            response.append(pub_dict)

        return response




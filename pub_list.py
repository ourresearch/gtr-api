from multiprocessing.pool import ThreadPool
from time import time as timer
import requests
from collections import Counter
from collections import defaultdict

from annotation_list import AnnotationList

# approach from https://stackoverflow.com/a/21130146/596939
def multi_run_wrapper(args):
   return farm_out_call(*args)

def farm_out_call(my_pub, method_name):
    my_method = getattr(my_pub, method_name)
    response = my_method()
    return response

class PubList(object):

    def __init__(self, pubs):
        self.pubs = pubs

    def set_dandelions(self):
        start = timer()

        my_thread_pool = ThreadPool(50)
        run_tuples = []
        my_pubs = self.pubs
        for my_pub in my_pubs:
            for run_dandelion_on in ["call_dandelion_on_article_title",
                                     "call_dandelion_on_abstract",
                                     "call_dandelion_on_short_abstract"]:
                run_tuples += [(my_pub, run_dandelion_on)]

        results = my_thread_pool.imap_unordered(multi_run_wrapper, run_tuples)

        my_thread_pool.close()
        my_thread_pool.join()
        my_thread_pool.terminate()

        print("elapsed time spent calling dandelion: %s" % (timer() - start,))
        self.pubs = my_pubs
        return my_pubs

    def set_annotations_and_pictures(self):
        my_pubs = self.set_dandelions()
        chosen_image_urls = set()

        # get annotations distribution, so pubs can use this to boost rare mentions
        annotation_counter = Counter()
        for my_pub in my_pubs:
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

        for my_pub in my_pubs:
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

        self.pubs = my_pubs


    def to_dict_serp_list(self, full=True):

        self.set_annotations_and_pictures()

        response = []
        for my_pub in self.pubs:

            pub_dict = my_pub.to_dict_serp(full)

            if hasattr(my_pub, "image") and my_pub.image:
                pub_dict["image"] = my_pub.image.to_dict_simple()
            else:
                pub_dict["image"] = {}

            pub_dict["topics"] = my_pub.topics

            pub_dict["annotations"] = {"using_article_abstract_short": None, "using_article_title": None}

            if hasattr(my_pub, "dandelion_title_annotation_list") and my_pub.dandelion_title_annotation_list:
                pub_dict["annotations"]["using_article_title"] = my_pub.dandelion_title_annotation_list.to_dict_simple()

            if hasattr(my_pub, "dandelion_short_abstract_annotation_list") and my_pub.dandelion_short_abstract_annotation_list:
                pub_dict["annotations"]["using_article_abstract_short"] = my_pub.dandelion_short_abstract_annotation_list.to_dict_simple()

            if full:
                if hasattr(my_pub, "dandelion_abstract_annotation_list") and my_pub.dandelion_abstract_annotation_list:
                    pub_dict["annotations"]["using_article_abstract"] = my_pub.dandelion_abstract_annotation_list.to_dict_simple()

            response.append(pub_dict)

        return response




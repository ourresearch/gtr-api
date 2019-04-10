from multiprocessing.pool import ThreadPool
from time import time as timer

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
    "Systematic_review"
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


class ResultSet(object):

    def __init__(self, pubs):
        self.pubs = pubs

    def set_dandelions(self):
        start = timer()
        my_thread_pool = ThreadPool(25)

        results = my_thread_pool.imap(call_dandelion_on_article_title, self.pubs)
        for result, pmid, error in results:
            if error:
                print "error fetching", pmid

        results = my_thread_pool.imap(call_dandelion_on_abstract, self.pubs)
        for result, pmid, error in results:
            if error:
                print "error fetching", pmid

        print("Elapsed Time: %s" % (timer() - start,))


    def set_annotations_and_pictures(self):
        self.set_dandelions()

        for pub in self.pubs:
            pub.picture_candidates = []
            pub.image = {}
            hit = pub.dandelion_title_results
            if hit and hit.get("topEntities", None):

                top_entities = hit["topEntities"]
                annotations = dandelion_simple_annotation_dicts(hit)
                for top_entity in top_entities:

                    picture_name = top_entity["uri"].rsplit("/", 1)[1]
                    if picture_name not in image_blacklist:
                        top_entity["annotation"] = [a for a in annotations if a["uri"]==top_entity["uri"]][0]
                        pub.picture_candidates.append(top_entity)

            pub.picture_candidates.reverse()
            for candidate in pub.picture_candidates:
                if candidate["annotation"].get("image_url", None):
                    pub.image = {"url": candidate["annotation"]["image_url"]}

    def to_dict_serp_list(self):

        self.set_annotations_and_pictures()

        response = []
        for my_pub in self.pubs:
            pub_dict = my_pub.to_dict_serp()
            pub_dict["picture_candidates"] = my_pub.picture_candidates
            pub_dict["image"] = my_pub.image
            pub_dict["annotations"] = {"using_article_abstract": None, "using_article_title": None}
            if hasattr(my_pub, "dandelion_abstract_results"):
                pub_dict["annotations"]["using_article_abstract"] = dandelion_simple_annotation_dicts(my_pub.dandelion_abstract_results)
            if hasattr(my_pub, "dandelion_title_results"):
                pub_dict["annotations"]["using_article_title"] = dandelion_simple_annotation_dicts(my_pub.dandelion_title_results)

            response.append(pub_dict)

        return response



def dandelion_simple_annotation_dicts(dandelion_raw):
    if not dandelion_raw:
        return []

    response_list = []
    for raw_annotation in dandelion_raw["annotations"]:
        response = {}
        keep_keys = [
            "start",
            "end",
            "confidence",
            "id",
            "title",
            "uri",
            "abstract",
            "label"
        ]
        for key in raw_annotation.keys():
            if key in keep_keys:
                response[key] = raw_annotation[key]
        if "image" in raw_annotation and raw_annotation["image"]:
            response["image_url"] = raw_annotation["image"]["full"]
        response_list.append(response)

    return response_list
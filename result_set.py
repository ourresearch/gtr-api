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

def fetch_url(pub):
    try:
        response_data = pub.call_dandelion(pub.article_title)
        return (response_data, pub.pmid, None)
    except Exception as e:
        return (None, pub.pmid, e)


class ResultSet(object):

    def __init__(self, pubs):
        self.pubs = pubs

    def set_dandelions(self):
        start = timer()
        results = ThreadPool(50).imap(fetch_url, self.pubs)
        for result, pmid, error in results:
            if error:
                print "error fetching", pmid
        print("Elapsed Time: %s" % (timer() - start,))

    def set_pictures(self):
        self.set_dandelions()

        for pub in self.pubs:
            pub.picture_candidates = []
            pub.image = {}
            hit = pub.dandelion_results
            if hit and hit.get("topEntities", None):

                top_entities = hit["topEntities"]
                annotations = hit["annotations"]
                for top_entity in top_entities:

                    picture_name = top_entity["uri"].rsplit("/", 1)[1]
                    if picture_name not in image_blacklist:
                        top_entity["annotation"] = [a for a in annotations if a["uri"]==top_entity["uri"]][0]
                        pub.picture_candidates.append(top_entity)

            if pub.picture_candidates:
                pub.image = {"url": pub.picture_candidates[0]["annotation"]["image"].get("full", None)}

    def to_dict_serp_list(self):

        self.set_pictures()

        response = []
        for my_pub in self.pubs:
            pub_dict = my_pub.to_dict_serp()
            pub_dict["picture_candidates"] = my_pub.picture_candidates
            pub_dict["image"] = my_pub.image
            response.append(pub_dict)

        return response




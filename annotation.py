from multiprocessing.pool import ThreadPool
from time import time as timer
import requests

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

class Annotation(object):

    def __init__(self, dandelion_raw):
        self.dandelion_raw = dandelion_raw
        self.is_top_entity = False
        self.top_entity_score = 0

    @property
    def uri(self):
        return self.dandelion_raw["uri"]

    @property
    def types(self):
        return self.dandelion_raw["types"]

    @property
    def image_url(self):
        if "image" in self.dandelion_raw and self.dandelion_raw["image"]:
            return self.dandelion_raw["image"]["full"]
        else:
            return None

    @property
    def picture_score(self):
        score = self.top_entity_score

        picture_name = self.uri.rsplit("/", 1)[1]
        if picture_name in image_blacklist:
            return 0

        if "http://dbpedia.org/ontology/Location" in self.types:
            score += 1

        if "http://dbpedia.org/ontology/Species" in self.types:
            score += 1

        return score


    def to_dict_simple(self):
        if not self.dandelion_raw:
            return []

        raw_annotation = self.dandelion_raw
        response = {}
        keep_keys = [
            "start",
            "end",
            "confidence",
            "id",
            "title",
            "uri",
            "abstract",
            "label",
            # "categories",
            "types"
        ]
        for key in raw_annotation.keys():
            if key in keep_keys:
                response[key] = raw_annotation[key]

        response["image_url"] = self.image_url
        response["url"] = self.image_url  # this is where it is expected for the picture
        response["picture_score"] = self.picture_score

        return response

    def get_picture_from_wikipedia(self):
        pass
            # url_template = u"https://en.wikipedia.org/w/api.php?action=query&prop=pageimages&format=json&piprop=original&titles={title}"
            # url = url_template.format(title=response["title"])
            # print "calling to get an image"
            # r = requests.get(url)
            # data = r.json()
            # print "done"
            #
            # if "query" in data and data["query"].get("pages", None):
            #     if data["query"]["pages"].values()[0].get("original", None):
            #         response["image_url"] = data["query"]["pages"].values()[0]["original"]["source"]
            #         print "success", response["image_url"]


from multiprocessing.pool import ThreadPool
from time import time as timer
import requests


image_blacklist = [
    "Prospective_cohort_study",
    "Patient",
    # "Randomized_controlled_trial",
    "Scientific_method",
    "Therapy",
    "Health",
    "Statistical_population",
    "Clinical_trial",
    "Risk",
    "Meta-analysis",
    "Systematic_review",
    "Human_sexual_activity",
    "Adult",
    "Death",
    "Therapy",
    "Old_world",
    "Experiment",
    "Scientific_control",
    "Conservatism"
    ]

class Annotation(object):

    def __init__(self, dandelion_raw):
        self.dandelion_raw = dandelion_raw
        self.is_top_entity = False
        self.top_entity_score = 0
        self.annotation_distribution = None

    @property
    def uri(self):
        return self.dandelion_raw["uri"]

    @property
    def spot(self):
        return self.dandelion_raw["spot"]

    @property
    def types(self):
        return self.dandelion_raw["types"]

    @property
    def confidence(self):
        return self.dandelion_raw["confidence"]

    @property
    def title(self):
        return self.dandelion_raw["title"]

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
            return -1000

        if not self.image_url:
            return -1000

        if "http://dbpedia.org/ontology/Location" in self.types:
            score += 1

        if "http://dbpedia.org/ontology/Species" in self.types:
            score += 1

        # because earth picture is bad, and it often matches global
        if self.title.lower() == "earth":
            score -= 1

        if self.spot.lower() == "activity" and self.title.lower() == "physical exercise":
            score -= 10

        if self.confidence < 0.6:
            score -= 1

        score += 0.1 * self.confidence

        if hasattr(self, "annotation_distribution") and self.annotation_distribution:
            score += 0.5 * (1 - self.annotation_distribution[self.image_url])

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
            "spot",
            # "categories",
            "types",
            "alternate_labels"
        ]
        for key in raw_annotation.keys():
            if key in keep_keys:
                response[key] = raw_annotation[key]

        response["image_url"] = self.image_url
        response["url"] = self.image_url  # this is where it is expected for the picture
        response["picture_score"] = self.picture_score
        response["raw_top_entity_score"] = self.top_entity_score
        if hasattr(self, "attribution_distribution"):
            response["attribution_distribution"] = self.attribution_distribution

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


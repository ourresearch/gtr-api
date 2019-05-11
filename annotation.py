from multiprocessing.pool import ThreadPool
from time import time as timer
import requests

annotation_file_contents = {}
fp = open("entities.tsv", "r")
lines = fp.readlines()
# skip header
for line in lines[1:]:
    (image_uri, annotation_title, orig_image_url, n, bad_image_reason, alt_img, weight, comment) = line.split("\t")
    if alt_img == "NEWPIC":
        alt_img = "https://i.imgur.com/J4ABZlG.png"
    annotation_file_contents[image_uri] = {
        "image_uri": image_uri,
        "annotation_title": annotation_title,
        "orig_image_url": orig_image_url,
        "n": n,
        "bad_image_reason": bad_image_reason,
        "alt_img": alt_img,
        "weight": weight,
        "comment": comment
    }
fp.close()


# because these annotations are almost always incorrectly applied and/or they are inappropriate
# should be in uri format
annotation_blacklist = [
    "Conservatism",
    "Film_editing", # gets tagged for gene editing 10.1056%2Fnejmcibr1716741
    "E.T._the_Extra-Terrestrial",  # gets tagged for et al 10.1093%2Fpubmed%2Ffdy038
    "IP_address", # gets mixed up with p-hacking 10.7717%2Fpeerj.3068
    "Facial_%28sex_act%29", # gets mixed up with facial 10.1016/j.jad.2007.01.031
]
annotation_blacklist = [a.lower() for a in annotation_blacklist]

# the annotations are fine we just don't want them to be our main image
# should be in uri format
image_blacklist = [
    ]
image_blacklist = [a.lower() for a in image_blacklist]

spot_requires_exact_match = [
    "cultivars"  # otherwise matches "Common Fig" and probably other common foods
]
spot_requires_exact_match = [a.lower() for a in spot_requires_exact_match]

annotation_requires_exact_match = [
    "Chemotherapy",  #sometimes matches therapy or treatment
    "Senescence", # otherwise matches "age"
    "Natural selection",  # otherwise matches "selective"
    "Diagnosis_of_HIV%2FAIDS", # otherwise matches testing
    "Grammatical_case",  #otherwise matches case
    "Musical_note",
    "Language_acquisition",
    "Common_law",
    "Observational_error",
    "Big_bang",
    "Art",
    "Thrombin",
    "Asian_americans",
    "French_third_republic",
    "Grief",
    "Mediation",
    "Social_change",
    "University_of_arizona",
    "Ancient_egypt",
    "Netherlands_national_football_team",
    "Profanity",
    "Medical_test",
    "Pollution",
    "Human_development_%28biology%29",
    "Risk_management",
    "Ocean_current",
    "Adoption",
    "British_raj"
    ]
annotation_requires_exact_match = [a.lower() for a in annotation_requires_exact_match]

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
    def in_image_blacklist(self):
        uri_name_for_matching = self.uri.lower().rsplit("/", 1)[1]
        if uri_name_for_matching in image_blacklist:
            return True
        return False

    @property
    def suppress(self):
        uri_name_for_matching = self.uri.lower().rsplit("/", 1)[1]
        spot_for_matching = self.spot.lower()

        if uri_name_for_matching in annotation_blacklist:
            return True

        if uri_name_for_matching in annotation_requires_exact_match:
            if uri_name_for_matching != spot_for_matching:
                return True

        if self.spot in spot_requires_exact_match:
            if uri_name_for_matching.replace("_", " ") != spot_for_matching:
                return True

        # too many incorrect hits on people, and they are too costly (remove this and search for "et al" to see)
        if "http://dbpedia.org/ontology/Person" in self.types:
            return True

        return False

    @property
    def image_url(self):
        # maybe supressed or not valid for some reason
        if self.suppress:
            return False

        if self.in_image_blacklist:
            return False

        if annotation_file_contents.get(self.uri, None):
            if annotation_file_contents[self.uri]["alt_img"]:
                return annotation_file_contents[self.uri]["alt_img"]

        if "image" in self.dandelion_raw and self.dandelion_raw["image"]:
            return self.dandelion_raw["image"]["full"]
        else:
            return None


    @property
    def topic_score(self):
        score = self.top_entity_score

        if self.suppress:
            return -1000

        if self.in_image_blacklist:
            return -1000

        # gotta avoid https://gettheresearch.org/search/pmdd?zoom=https%3A%2F%2Fdoi.org%2F10.1016%2Fj.jad.2007.01.031

        if "sex" in self.title.lower():
            score -= 2

        if "http://dbpedia.org/ontology/Location" in self.types and self.title not in ["Ancient Egypt"]:
            score += 2

        if "http://dbpedia.org/ontology/Species" in self.types and self.title not in ["Rat", "Mouse"]:
            score += 2

        if "http://dbpedia.org/ontology/AnatomicalStructure" in self.types:
            score += 1

        if "http://dbpedia.org/ontology/Biomolecule" in self.types:
            score += 0.8

        if "http://dbpedia.org/ontology/ChemicalSubstance" in self.types:
            score += 0.6

        if "http://dbpedia.org/ontology/Food" in self.types:
            score += 0.8

        if "http://dbpedia.org/ontology/SportsTeam" in self.types:
            score -= 1

        if "http://dbpedia.org/ontology/TelevisionEpisode" in self.types:
            score -= 10

        if "http://dbpedia.org/ontology/TelevisionShow" in self.types:
            score -= 10

        if self.spot.lower() == "activity" and self.title.lower() == "physical exercise":
            score -= 10

        if self.spot.lower() == "origins" and self.title.lower() == "fibonacci number":
            score -= 10

        if self.spot.lower() == "ages" and self.title.lower() == "ageing":
            score -= 10

        if self.confidence < 0.7:
            score -= 10

        score += 0.2 * self.confidence



        return score

    @property
    def picture_score(self):
        score = self.topic_score

        if annotation_file_contents.get(self.uri, None):
            if annotation_file_contents[self.uri]["bad_image_reason"]:
                return -1000

        if not self.image_url:
            return -1000

        if annotation_file_contents.get(self.uri, None) and annotation_file_contents[self.uri]["weight"]:
            score *= float(annotation_file_contents[self.uri]["weight"])

        if hasattr(self, "annotation_distribution") and self.annotation_distribution:
            score += 0.3 * (1 - self.annotation_distribution[self.image_url])

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


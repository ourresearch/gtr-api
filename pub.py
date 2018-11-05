import datetime
import shortuuid
import hashlib
import requests
from sqlalchemy.dialects.postgresql import JSONB

from app import db



class Pub(db.Model):
    __tablename__ = "medline_citation"
    pmid = db.Column(db.Numeric, primary_key=True)
    article_title = db.Column(db.Text)
    journal_title = db.Column(db.Text)
    abstract_text = db.Column(db.Text)
    pub_date_year = db.Column(db.Text)


    def get(self):
        self.metadata.get()
        self.open_access.get()
        self.altmetrics.get()

    @property
    def display_doi_url(self):
        if not self.doi:
            return None
        return u"https://doi.org/{}".format(self.doi)

    @property
    def doi(self):
        if not hasattr(self, "doi_url"):
            return None
        return self.doi_url.replace("https://doi.org/", "")

    @property
    def authors(self):
        return None

    @property
    def is_oa(self):
        self.get_open_access()
        if self.open_access_response:
            return self.open_access_response["is_oa"]
        return None

    @property
    def best_oa_location_dict(self):
        self.get_open_access()
        if self.open_access_response:
            return self.open_access_response["best_oa_location"]
        return None

    @property
    def all_oa_location_dicts(self):
        self.get_open_access()
        if self.open_access_response:
            return self.open_access_response["oa_locations"]
        return None

    def get_open_access(self):
        if not hasattr(self, "open_access_response"):
            self.open_access_response = None
            if not self.doi:
                return

            open_access_obj = Unpaywall(self.doi)
            if open_access_obj:
                open_access_obj.get()
                self.open_access_response = open_access_obj.data
                return self.open_access_response


    def get_nerd(self):
        if not self.abstract_text:
            return

        query_text = self.abstract_text
        query_text = query_text.replace("\n", " ")

        url = u"http://cloud.science-miner.com/nerd/service/disambiguate"
        payload = {
            "text": query_text,
            "shortText": "",
            "termVector": [],
            "language": {
                "lang": "en"
            },
            "entities": [],
            "mentions": [
                "ner",
                "wikipedia"
            ],
            "nbest": False,
            "sentence": False,
            "customisation": "generic"
        }
        headers = {
            "Content-disposition": "form-data"
        }
        r = requests.post(url, json=payload)
        response_data = r.json()
        import pprint
        pprint.pprint(response_data)
        return response_data

    def to_dict_full(self):
        print "calling nerd"
        nerd_results = self.get_nerd()
        print "done"

        results = self.to_dict_serp()
        results["nerd"] = nerd_results
        return results



    def to_dict_serp(self):

        self.open_access = Unpaywall(self.doi)
        self.open_access.get()
        # self.altmetrics = AltmetricsForDoi(self.doi)
        # self.altmetrics.get()

        response = {
            "pmid": self.pmid,
            "doi": self.doi,
            "doi_url": self.display_doi_url,
            "title": self.article_title,
            "abstract": self.abstract_text,
            "year": self.pub_date_year,
            "journal_name": self.journal_title,
            "published_date": None,

            "is_oa": self.is_oa,
            "best_oa_location": self.best_oa_location_dict,
            "oa_locations": self.all_oa_location_dicts,

            "snippet": getattr(self, "snippet", None),
            "score": getattr(self, "score", None),

            # "open_access": self.open_access.to_dict()

        }

        if self.authors:
            response["author_lastnames"] = [author.get("family", None) for author in self.authors]
        else:
            response["author_lastnames"] = []

        return response




class Unpaywall(object):
    def __init__(self, doi):
        self.doi = doi
        self.url = u"https://api.unpaywall.org/v2/{}?email=team+gtr@impactstory.org".format(doi)
        self.data = {}

    def get(self):
        if self.doi:
            r = requests.get(self.url)
            if r.status_code == 200:
                self.data = r.json()

    def to_dict(self):
        self.data["oadoi_url"] = self.url
        return self.data




class AltmetricsForDoi(object):

    def __init__(self, doi):
        self.doi = doi
        self.url = u"https://api.paperbuzz.org/{}?email=team+gtr@impactstory.org".format(doi)
        self.data = {}

    def get(self):
        if self.doi:
            r = requests.get(self.url)
            if r.status_code == 200:
                self.data = r.json()

    def to_dict(self):
        self.data["paperbuzz_url"] = self.url
        return self.data




class CrossrefMetadata(object):
    def __init__(self, doi):
        self.doi = doi
        self.url = u"https://api.crossref.org/works/{}/transform/application/vnd.citationstyles.csl+json".format(doi)
        self.data = {}

    def get(self):
        if self.doi:
            r = requests.get(self.url)
            if r.status_code == 200:
                self.data = r.json()

    def to_dict(self):
        self.data["crossref_url"] = self.url
        return self.data


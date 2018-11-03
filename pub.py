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
    def doi(self):
        if not getattr(self, "doi_url"):
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

            open_access_obj = OaDoi(self.doi)
            if open_access_obj:
                open_access_obj.get()
                self.open_access_response = open_access_obj.data
                return self.open_access_response



    def to_dict_serp(self):

        self.open_access = OaDoi(self.doi)
        self.open_access.get()
        # self.altmetrics = AltmetricsForDoi(self.doi)
        # self.altmetrics.get()

        response = {
            "pmid": self.pmid,
            "doi": self.doi,
            "doi_url": getattr(self, "doi_url"),
            "title": self.article_title,
            "abstracts": self.abstract_text,
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




class OaDoi(object):
    def __init__(self, doi):
        self.doi = doi
        self.url = u"https://api.oadoi.org/v2/{}?email=team+gtr@impactstory.org".format(doi)
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


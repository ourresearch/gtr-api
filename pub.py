import datetime
import shortuuid
import hashlib
import requests
from sqlalchemy.dialects.postgresql import JSONB

from app import db


class MedlineAuthor(db.Model):
    __tablename__ = "medline_author"
    pmid = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'), primary_key=True)
    last_name = db.Column(db.Text, primary_key=True)


class Pub(db.Model):
    __tablename__ = "medline_citation"
    pmid = db.Column(db.Numeric, primary_key=True)
    article_title = db.Column(db.Text)
    journal_title = db.Column(db.Text)
    abstract_text = db.Column(db.Text)
    pub_date_year = db.Column(db.Text)
    number_of_references = db.Column(db.Text)
    authors = db.relationship("MedlineAuthor")

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
    def author_lastnames(self):
        print self.authors
        response = None
        if self.authors:
            response = [author.last_name for author in self.authors]
        return response

    @property
    def display_is_oa(self):
        return getattr(self, "is_oa", None)

    @property
    def display_oa_url(self):
        return getattr(self, "oa_url", None)

    @property
    def display_best_host(self):
        return getattr(self, "best_host", None)

    @property
    def display_best_version(self):
        return getattr(self, "best_version", None)

    def get_nerd(self):
        if not self.abstract_text or len(self.abstract_text) <=3:
            return

        query_text = self.abstract_text
        query_text = query_text.replace("\n", " ")

        # url = u"http://cloud.science-miner.com/nerd/service/disambiguate"
        url = u"http://nerd.huma-num.fr/nerd/service/disambiguate"
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
        try:
            response_data = r.json()
        except ValueError:
            response_data = None
        return response_data

    def to_dict_full(self):
        print "calling nerd"
        nerd_results = self.get_nerd()
        print "done"

        results = self.to_dict_serp()
        results["nerd"] = nerd_results
        return results



    def to_dict_serp(self):

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
            "num_references_from_pmc": self.number_of_references,
            "author_lastnames": self.author_lastnames,

            "is_oa": self.display_is_oa,
            "oa_url": self.display_oa_url,
            "best_host": self.display_best_host,
            "best_version": self.display_best_version,

            "snippet": getattr(self, "snippet", None),
            "score": getattr(self, "score", None),
        }

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


import datetime
import shortuuid
import hashlib
import requests
from sqlalchemy.dialects.postgresql import JSONB

from app import db
from util import get_sql_answer

class MedlineAuthor(db.Model):
    __tablename__ = "medline_author"
    pmid = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'), primary_key=True)
    author_order = db.Column(db.Numeric, primary_key=True)
    last_name = db.Column(db.Text, primary_key=True)  # this one shouldn't have primary key once all orders are populated


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
    def pmid_url(self):
        return u"https://www.ncbi.nlm.nih.gov/pubmed/{}".format(self.pmid)

    @property
    def display_doi_url(self):
        if self.display_doi:
            return u"https://doi.org/{}".format(self.display_doi)
        return None

    @property
    def display_doi(self):
        if hasattr(self, "doi"):
            return self.doi
        q = "select doi from dois_pmid_lookup where pmid = {}::text".format(self.pmid)
        doi = get_sql_answer(db, q)
        return doi

    @property
    def sorted_authors(self):
        if not self.authors:
            return None
        authors = self.authors
        sorted_authors = sorted(authors, key=lambda x: x.author_order, reverse=False)
        return sorted_authors

    @property
    def author_lastnames(self):
        response = None
        if self.sorted_authors:
            response = [author.last_name for author in self.sorted_authors]
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
        nerd_results = self.get_nerd()

        results = self.to_dict_serp()
        results["nerd"] = nerd_results
        results["doi"] = self.display_doi
        results["paperbuzz"] = get_paperbuzz(self.display_doi)

        return results



    def to_dict_serp(self):

        # self.altmetrics = AltmetricsForDoi(self.doi)
        # self.altmetrics.get()

        response = {
            "pmid": self.pmid,
            "pmid_url": self.pmid_url,
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





def get_paperbuzz(doi):
    if not doi:
        return None

    data = None
    url = u"https://api.paperbuzz.org/v0/doi/{}?email=team+gtr@impactstory.org".format(doi)
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
    return data

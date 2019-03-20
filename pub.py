import datetime
import shortuuid
import hashlib
import requests
from collections import defaultdict
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import sql

from app import db
from util import get_sql_answer
from util import run_sql

class Author(db.Model):
    __tablename__ = "medline_author"
    pmid = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'), primary_key=True)
    author_order = db.Column(db.Numeric, primary_key=True)
    last_name = db.Column(db.Text, primary_key=True)  # this one shouldn't have primary key once all orders are populated

class PubOtherId(db.Model):
    __tablename__ = "medline_citation_other_id"
    pmid = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'), primary_key=True)
    source = db.Column(db.Text, primary_key=True)
    other_id = db.Column(db.Text)

class PubType(db.Model):
    __tablename__ = "medline_article_publication_type"
    pmid = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'), primary_key=True)
    publication_type = db.Column(db.Text, primary_key=True)

class PubMesh(db.Model):
    __tablename__ = "medline_mesh_heading"
    pmid = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'), primary_key=True)
    descriptor_name = db.Column(db.Text)
    descriptor_name_major_yn = db.Column(db.Text, primary_key=True)
    qualifier_name = db.Column(db.Text)
    qualifier_name_major_yn = db.Column(db.Text, primary_key=True)

    def to_dict(self):
        response = {}
        response["descriptor"] = self.descriptor_name
        if self.descriptor_name_major_yn == "Y":
            response["descriptor_is_major"] = True
        if self.qualifier_name and self.qualifier_name != "N/A":
            response["qualifier_name"] = self.qualifier_name.replace("&amp;", "and")
            if self.qualifier_name_major_yn == "Y":
                response["qualifier_is_major"] = True
        return response

class Unpaywall(db.Model):
    __tablename__ = "bq_pubmed_doi_unpaywall_pmid_numeric_mv"
    doi = db.Column(db.Text)
    pmid = db.Column(db.Text, primary_key=True)
    pmid_numeric = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'))
    pmcid = db.Column(db.Text)
    is_oa = db.Column(db.Boolean)
    best_host_type = db.Column(db.Text)
    best_version = db.Column(db.Text)
    oa_url = db.Column(db.Text)

class DoiLookup(db.Model):
    __tablename__ = "dois_pmid_lookup_pmid_numeric_mv"
    doi = db.Column(db.Text, primary_key=True)
    pmid_numeric = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'))
    paperbuzz = db.relationship("Paperbuzz", uselist=False, lazy='subquery')

class Paperbuzz(db.Model):
    __tablename__ = "dois_with_ced_events"
    doi = db.Column(db.Text, db.ForeignKey(DoiLookup.doi), primary_key=True)
    num_events = db.Column(db.Numeric)


class Pub(db.Model):
    __tablename__ = "medline_citation"
    pmid = db.Column(db.Numeric, primary_key=True)
    article_title = db.Column(db.Text)
    journal_title = db.Column(db.Text)
    abstract_text = db.Column(db.Text)
    pub_date_year = db.Column(db.Text)
    date_of_electronic_publication = db.Column(db.Text)
    authors = db.relationship("Author", lazy='subquery')
    pub_other_ids = db.relationship("PubOtherId", lazy='subquery')
    pub_types = db.relationship("PubType", lazy='subquery')
    mesh = db.relationship("PubMesh", lazy='subquery')
    doi_lookup = db.relationship("DoiLookup", uselist=False, lazy='subquery')
    unpaywall_lookup = db.relationship("Unpaywall", uselist=False, lazy='subquery')

    @property
    def paperbuzz(self):
        if self.doi_lookup and self.doi_lookup.paperbuzz:
            return int(self.doi_lookup.paperbuzz.num_events)
        return 0

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
        if not self.doi_lookup:
            return None
        return self.doi_lookup.doi

    @property
    def sorted_authors(self):
        if not self.authors:
            return None
        authors = self.authors
        sorted_authors = sorted(authors, key=lambda x: x.author_order, reverse=False)
        return sorted_authors

    @property
    def author_lastnames(self):
        response = []
        if self.sorted_authors:
            response = [author.last_name for author in self.sorted_authors]
        return response


    @property
    def display_number_of_paperbuzz_events(self):
        return self.paperbuzz

    @property
    def display_is_oa(self):
        if self.unpaywall_lookup:
            return self.unpaywall_lookup.is_oa
        return None

    @property
    def display_oa_url(self):
        if self.unpaywall_lookup:
            return self.unpaywall_lookup.oa_url
        return None

    @property
    def display_best_host(self):
        if self.unpaywall_lookup:
            return self.unpaywall_lookup.best_host_type
        return None

    @property
    def display_best_version(self):
        if self.unpaywall_lookup:
            return self.unpaywall_lookup.best_version
        return None

    @property
    def display_pub_types(self):
        response = []
        for pub_type in self.pub_types:
            include_it = True
            excludes = ["Journal Article", "Research Support"]
            for exclude_phrase in excludes:
                if exclude_phrase in pub_type.publication_type:
                    include_it = False
            if include_it:
                response += [pub_type.publication_type]
        return response

    def get_nerd(self):
        if not self.abstract_text or len(self.abstract_text) <=3:
            return

        print u"calling paperbuzz with {}".format(self.pmid)

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


    @property
    def short_abstract(self):
        if not self.abstract_text:
            return self.abstract_text

        response = ""

        if "CONCLUSION:" in self.abstract_text:
            response = self.abstract_text.rsplit("CONCLUSION:", 1)[1]
        elif "CONCLUSIONS:" in self.abstract_text:
            response = self.abstract_text.rsplit("CONCLUSIONS:", 1)[1]
        else:
            response = "... "
            try:
                response += ". ".join(self.abstract_text.rsplit(". ", 3)[1:])
            except IndexError:
                response += self.abstract_text[-500:-1]
        return response

    @property
    def adjusted_score(self):
        score = getattr(self, "score", 0)

        if self.journal_title and "Cochrane database" in self.journal_title:
            score += 10

        if "Consensus Development Conference" in self.display_pub_types:
            score += 7
        if "Practice Guideline" in self.display_pub_types:
            score += 7
        if "Guideline" in self.display_pub_types:
            score += 7
        if "Review" in self.display_pub_types:
            score += 3
        if "Meta-Analysis" in self.display_pub_types:
            score += 3
        if "Randomized Controlled Trial" in self.display_pub_types:
            score += 2
        if "Clinical Trial" in self.display_pub_types:
            score += 1
        if "Comparative Study" in self.display_pub_types:
            score += 0.5
        if "Case Reports" in self.display_pub_types:
            score += -5
        if "English Abstract" in self.display_pub_types:
            score += -5

        return score

    def to_dict_full(self):
        nerd_results = self.get_nerd()

        # commented out while we wait for a shorter, faster paperbuzz api result
        # paperbuzz_results = get_paperbuzz(self.display_doi)
        paperbuzz_results = None

        results = self.to_dict_serp()
        results["nerd"] = nerd_results
        results["paperbuzz"] = paperbuzz_results
        results["abstract"] = self.abstract_text

        return results



    def to_dict_serp(self):

        response = {
            "pmid": self.pmid,
            "pmid_url": self.pmid_url,
            "doi": self.display_doi_url,
            "doi_url": self.display_doi_url,
            "title": self.article_title,
            "short_abstract": self.short_abstract,
            "year": self.pub_date_year,
            "journal_name": self.journal_title,
            "date_of_electronic_publication": self.date_of_electronic_publication,
            "num_paperbuzz_events": self.display_number_of_paperbuzz_events,
            "author_lastnames": self.author_lastnames,
            "is_oa": self.display_is_oa,
            "oa_url": self.display_oa_url,
            "best_host": self.display_best_host,
            "best_version": self.display_best_version,
            "pub_types": self.display_pub_types,
            "mesh": [m.to_dict() for m in self.mesh],

            "snippet": getattr(self, "snippet", None),
            "score": self.adjusted_score
        }

        return response





def get_paperbuzz(doi):
    if not doi:
        return None

    print u"calling paperbuzz with {}".format(doi)
    data = None
    url = u"https://api.paperbuzz.org/v0/doi/{}?email=team+gtr@impactstory.org".format(doi)
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
    return data

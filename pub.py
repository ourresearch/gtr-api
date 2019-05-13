#!/usr/local/bin/python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import os
import re
import datetime
import shortuuid
import hashlib
import requests
import random
import json
from urllib import quote_plus
from collections import defaultdict
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import sql
from sqlalchemy import func
from sqlalchemy.orm import deferred
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from sqlalchemy.orm import column_property

from app import db
from annotation_list import AnnotationList
from util import get_sql_answer
from util import run_sql
from util import TooManyRequestsException


def call_dandelion(query_text_raw, batch_api_key=None):
    # print "CALLING DANDELION"
    if not query_text_raw:
        return None

    if batch_api_key:
        api_key = batch_api_key
    else:
        api_key = os.getenv("DANDELION_API_KEY")

    query_text = quote_plus(query_text_raw.encode('utf-8'), safe=':/'.encode('utf-8'))

    # if the query text is very short, don't autodetect the language, try it as english
    language = "auto"
    if len(query_text) < 40:
        language = "en"

    url_template = u"https://api.dandelion.eu/datatxt/nex/v1/?min_confidence=0.5&text={query}&lang={language}&country=-1&social=False&top_entities=8&include=image,abstract,types,categories,alternate_labels,lod&token={api_key}"
    url = url_template.format(query=query_text, language=language, api_key=api_key)
    r = requests.get(url)
    if r.headers.get("X-DL-units-left", None) == 0 or r.status_code == 401:
        print u"TooManyRequestsException"
        raise TooManyRequestsException

    try:
        response_data = r.json()
    except ValueError:
        response_data = None

    return response_data


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

class DoiLookup(db.Model):
    __tablename__ = "bq_pubmed_doi_unpaywall"
    doi = db.Column(db.Text, primary_key=True)
    pmid = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'))
    pmcid = db.Column(db.Text)
    is_oa = db.Column(db.Boolean)
    best_host_type = db.Column(db.Text)
    best_version = db.Column(db.Text)
    oa_url = db.Column(db.Text)
    published_date = db.Column(db.DateTime)
    paperbuzz = db.relationship("Paperbuzz", uselist=False, lazy='subquery')
    news = db.relationship("News", lazy='subquery')

class Paperbuzz(db.Model):
    __tablename__ = "dois_with_ced_events_mv"
    doi = db.Column(db.Text, db.ForeignKey(DoiLookup.doi), primary_key=True)
    num_events = db.Column(db.Numeric)

class News(db.Model):
    __tablename__ = "local_newsfeed_events_mv"
    event_id = db.Column(db.Text, primary_key=True)
    doi = db.Column(db.Text, db.ForeignKey(DoiLookup.doi))
    news_url = db.Column(db.Text)
    news_title = db.Column(db.Text)
    occurred_at = db.Column(db.DateTime)

    def to_dict(self):
        response = {
            "news_url": self.news_url,
            "news_title": self.news_title,
            "occurred_at": self.occurred_at
        }
        return response


class Dandelion(db.Model):
    __tablename__ = "dois_paperbuzz_dandelion"
    doi = db.Column(db.Text, primary_key=True)
    pmid = db.Column(db.Numeric, db.ForeignKey('medline_citation.pmid'), primary_key=True)
    num_events = db.Column(db.Numeric)
    dandelion_collected = db.Column(db.DateTime)
    dandelion_raw_article_title = db.Column(JSONB)
    dandelion_raw_abstract_text = db.Column(db.Text)

    def __repr__(self):
        return u'<Dandelion ({doi}) {num_events}>'.format(
            doi=self.doi,
            num_events=self.num_events
        )


class Pub(db.Model):
    __tablename__ = "medline_citation"
    pmid = db.Column(db.Numeric, primary_key=True)
    journal_title = db.Column(db.Text)
    abstract_text = db.Column(db.Text)
    article_title = deferred(db.Column(db.Text), group="full")
    pub_date_year = deferred(db.Column(db.Text), group="full")
    authors = db.relationship("Author", lazy='subquery')
    pub_types = db.relationship("PubType", lazy='subquery')
    doi_lookup = db.relationship("DoiLookup", uselist=False, lazy='subquery')
    dandelion_lookup = db.relationship("Dandelion", uselist=False, lazy='subquery')
    # pub_other_ids = db.relationship("PubOtherId", lazy='subquery')
    # mesh = db.relationship("PubMesh", lazy='subquery')
    abstract_length = column_property(func.char_length(abstract_text))

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
    def dandelion_title(self):
        if self.dandelion_lookup:
            return self.dandelion_lookup.dandelion_raw_article_title
        return None

    @property
    def dandelion_abstract(self):
        if self.dandelion_lookup:
            return self.dandelion_lookup.dandelion_raw_abstract_text
        return None


    @property
    def dandelion_has_been_collected(self):
        if self.dandelion_lookup:
            if self.dandelion_lookup.dandelion_collected:
                return True
        return False

    @property
    def display_is_oa(self):
        if self.doi_lookup:
            return self.doi_lookup.is_oa
        return None

    @property
    def display_published_date(self):
        if self.doi_lookup:
            return self.doi_lookup.published_date.isoformat()[0:10]
        return None

    @property
    def display_oa_url(self):
        if self.doi_lookup:
            return self.doi_lookup.oa_url
        return None

    @property
    def display_best_host(self):
        if self.doi_lookup:
            return self.doi_lookup.best_host_type
        return None

    @property
    def display_best_version(self):
        if self.doi_lookup:
            return self.doi_lookup.best_version
        return None

    @property
    def news_articles(self):
        if self.doi_lookup and self.doi_lookup.news:
            articles = sorted(self.doi_lookup.news, key=lambda x: x.occurred_at, reverse=True)
            return articles
        return []

    @property
    def dandelion_abstract_annotation_list(self):
        if hasattr(self, "fresh_dandelion_abstract_annotation_list"):
            return self.fresh_dandelion_abstract_annotation_list
        if self.dandelion_has_been_collected:
            dandelion_results = json.loads(self.dandelion_lookup.dandelion_raw_abstract_text)
            return AnnotationList(dandelion_results)
        return None

    @property
    def dandelion_title_annotation_list(self):
        if hasattr(self, "fresh_dandelion_article_annotation_list"):
            return self.fresh_dandelion_article_annotation_list
        if self.dandelion_has_been_collected:
            dandelion_results = self.dandelion_lookup.dandelion_raw_article_title
            return AnnotationList(dandelion_results)
        return None

    def call_dandelion_on_abstract(self):
        if not self.dandelion_has_been_collected:
            if self.abstract_text:
                dandelion_results = call_dandelion(self.abstract_text)
                self.fresh_dandelion_abstract_annotation_list = AnnotationList(dandelion_results)

    def call_dandelion_on_article_title(self):
        if not self.dandelion_has_been_collected:
            if self.article_title:
                dandelion_results = call_dandelion(self.article_title)
                self.fresh_dandelion_article_annotation_list = AnnotationList(dandelion_results)

    @property
    def annotations_for_pictures(self):
        try:
            return self.dandelion_title_annotation_list.list()
        except:
            return []

    @property
    def topics(self):
        try:
            topic_annotation_objects = sorted(self.dandelion_title_annotation_list.list(), key=lambda x: x.topic_score, reverse=True)
            response = [a.title for a in topic_annotation_objects]
        except:
            response = []
        return response


    def set_annotation_distribution(self, annotation_distribution):
        for my_annotation in self.annotations_for_pictures:
            my_annotation.annotation_distribution = annotation_distribution


    def abstract_with_annotations_dict(self, full=True):
        sections = []
        if self.abstract_structured:
            sections = self.abstract_structured
        elif self.abstract_text:
            background_text = ""
            summary_text = ""
            if "CONCLUSION:" in self.abstract_text:
                background_text = self.abstract_text.rsplit("CONCLUSION:", 1)[0]
                summary_text = self.abstract_text.rsplit("CONCLUSION:", 1)[1]
            elif "CONCLUSIONS:" in self.abstract_text:
                background_text = self.abstract_text.rsplit("CONCLUSIONS:", 1)[0]
                summary_text = self.abstract_text.rsplit("CONCLUSIONS:", 1)[1]
            else:
                try:
                    background_text += ". ".join(self.abstract_text.rsplit(". ", 3)[0:1]) + "."
                    summary_text += ". ".join(self.abstract_text.rsplit(". ", 3)[1:])
                except IndexError:
                    background_text += self.abstract_text[-500:-1]
                    summary_text += self.abstract_text[-500:-1]

            background_text = background_text.strip()
            summary_text = summary_text.strip()

            sections = [
                {"text": background_text, "heading": "BACKGROUND", "section_split_source": "automated", "summary": False, "original_start":0, "original_end":len(background_text)},
                {"text": summary_text, "heading": "SUMMARY", "section_split_source": "automated", "summary": True, "original_start":len(background_text)+2, "original_end":len(self.abstract_text)}
            ]

        if full:
            for section in sections:
                section["annotations"] = []
                if hasattr(self, "dandelion_abstract_annotation_list"):
                    for anno in self.dandelion_abstract_annotation_list.list():
                        if anno.confidence >= 0.65:
                            if anno.start >= section["original_start"] and anno.end <= section["original_end"]:
                                my_anno_dict = anno.to_dict_simple()
                                my_anno_dict["start"] -= section["original_start"]
                                my_anno_dict["end"] -= section["original_start"] - 1
                                section["annotations"] += [my_anno_dict]

        if not full:
            sections = [s for s in sections if s["summary"]==True]

        return sections


    def title_annotations_dict(self, full=True):
        response = []
        if full:
            if self.dandelion_title_annotation_list:
                response = self.dandelion_title_annotation_list.to_dict_simple()
        return response

    def get_nerd(self):
        if not self.abstract_text or len(self.abstract_text) <=3:
            return

        print u"calling nerd with {}".format(self.pmid)

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
    def abstract_structured(self):
        all_sections = []

        if self.abstract_text and re.findall("(^[A-Z]{4,}): ", self.abstract_text):
            matches = re.findall("([A-Z' ,]{4,}): (.*?) (?=$|[A-Z' ,]{4,}: )", self.abstract_text)
            for match in matches:
                all_sections.append({
                    "heading": match[0],
                    "text": match[1]
                })

        cursor = 0
        for section in all_sections:
            cursor += len(section["heading"])
            cursor += 2
            # don't include heading in what can be annotated
            section["original_start"] = cursor
            cursor += len(section["text"])
            section["original_end"] = cursor
            cursor += 1
            section["section_split_source"] = "structured"
            section["summary"] = False

        if all_sections:
            all_sections[-1]["summary"] = True
        return all_sections


    @property
    def suppress(self):
        if self.display_pub_types:
            pub_type_pubmed = [p["pub_type_pubmed"] for p in self.display_pub_types]
            if "Retracted Publication" in pub_type_pubmed:
                return True
        return False

    @property
    def adjusted_score(self):
        score = getattr(self, "score", 0)

        if self.abstract_length < 10:
            score -= 5

        if self.journal_title and "cochrane database" in self.journal_title.lower():
            score += 10

        if not self.paperbuzz:
            score -= 5

        if self.news_articles:
            score += 1

        if self.display_pub_types:
            pub_type_pubmed = [p["pub_type_pubmed"] for p in self.display_pub_types]
            if "Consensus Development Conference" in pub_type_pubmed:
                score += 7
            if "Practice Guideline" in pub_type_pubmed:
                score += 7
            if "Guideline" in pub_type_pubmed:
                score += 7
            if "Review" in pub_type_pubmed:
                score += 3
            if "Meta-Analysis" in pub_type_pubmed:
                score += 3
            if "Randomized Controlled Trial" in pub_type_pubmed:
                score += 2
            if "Clinical Trial" in pub_type_pubmed:
                score += 1
            if "Comparative Study" in pub_type_pubmed:
                score += 0.5
            if "Case Reports" in pub_type_pubmed:
                score += -5
            if "English Abstract" in pub_type_pubmed:
                score += -5

        return score

    @property
    def display_pub_types(self):

        pub_type_data = [
            ['Meta-Analysis', 'meta-analysis', 5],
            ['Systematic Review', 'review', 5],
            ['Practice Guideline', 'guidelines', 5],
            ['Guideline', 'guidelines', 5],
            ['Consensus Development Conference', 'review', 5],
            ['Patient Education Handout', 'guidelines', 5],
            ['Review', 'review', 4],
            ['Introductory Journal Article', 'review', 4],
            ['Randomized Controlled Trial', 'randomized controlled trial', 3.5],
            ['Clinical Trial', 'clinical trial', 3],
            ['Controlled Clinical Trial', 'clinical trial', 3],
            ['Case Reports', 'case study', 2],
            ['Comparative Study', 'research study', 2],
            ['Evaluation Studies', 'research study', 2],
            ['Validation Studies', 'research study', 2],
            ['Observational Study', 'research study', 2],
            ['Clinical Trial, Phase II', 'clinical trial', 2],
            ['Clinical Trial, Phase I', 'clinical trial', 2],
            ['Clinical Trial, Phase III', 'clinical trial', 2],
            ['Letter', 'editorial content', 1],
            ['Comment', 'editorial content', 1],
            ['Editorial', 'editorial content', 1],
            ['News', 'news and interest', 1],
            ['Biography', 'news and interest', 1],
            ['Published Erratum', 'editorial content', 1],
            ['Portraits', 'news and interest', 1],
            ['Interview', 'news and interest', 1],
            ['Newspaper Article', 'news and interest', 1],
            ['Retraction of Publication', 'editorial content', 1],
            ['Portrait', 'news and interest', 1],
            ['Autobiography', 'news and interest', 1],
            ['Personal Narratives', 'news and interest', 1],
            ['Retracted Publication', 'retracted', -1]]
        pub_type_lookup = dict(zip([name for (name, label, val) in pub_type_data], pub_type_data))

        response = []
        if not self.pub_types:
            return response

        for pub_type in self.pub_types:
            pub_type_name = pub_type.publication_type
            if pub_type_name in pub_type_lookup:
                response.append({"pub_type_pubmed": pub_type_lookup[pub_type_name][0],
                                 "pub_type_gtr": pub_type_lookup[pub_type_name][1],
                                 "evidence_level": pub_type_lookup[pub_type_name][2]
                })
            else:
                include_it = True
                excludes = ["Journal Article", "Research Support"]
                for exclude_phrase in excludes:
                    if exclude_phrase in pub_type_name:
                        include_it = False
                if include_it:
                    response.append({"pub_type_pubmed": pub_type_name,
                                 "pub_type_gtr": None,
                                 "evidence_level": None})

        response = sorted(response, key=lambda x: x["evidence_level"] or 0, reverse=True)
        return response



    def to_dict_serp(self, full=True):

        response = {
            "doi": self.display_doi,
            "doi_url": self.display_doi_url,
            "title": self.article_title,
            "year": self.pub_date_year,
            "journal_name": self.journal_title,
            "num_paperbuzz_events": self.display_number_of_paperbuzz_events,
            "is_oa": self.display_is_oa,
            "oa_url": self.display_oa_url,
            "oa_host": self.display_best_host,
            "oa_version": self.display_best_version,
            "published_date": self.display_published_date,
            "pub_types": self.display_pub_types,
            # "snippet": getattr(self, "snippet", None),
            "score": self.adjusted_score
        }

        if full:
            additional_items = {
            "pmid": self.pmid,
            "pmid_url": self.pmid_url,
            "author_lastnames": self.author_lastnames,
            # "mesh": [m.to_dict() for m in self.mesh],
            "news_articles": [a.to_dict() for a in self.news_articles]
            }
            response.update(additional_items)

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

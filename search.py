from sqlalchemy import sql
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import JSONB
from time import time
import requests
import re
import math
import decimal

from app import db
from pub import Pub
from pub import pub_type_lookup
from util import elapsed



def adjusted_score(my_dict):
    raw_score = my_dict.get("score")
    if not raw_score:
        raw_score = 0
    score = math.log10(.1 + raw_score) * 5

    if my_dict["abstract_length"] < 10:
        score -= 10

    # if my_dict["journal_title"] and "cochrane database" in my_dict["journal_title"].lower():
    #     score += 10

    if not my_dict["num_events"]:
        score -= 5

    if my_dict["num_news_events"]:
        score += math.log10(decimal.Decimal('0.1') + my_dict.get("num_news_events", 0)) * 4

    if my_dict["pub_types"]:
        pub_type_pubmed = my_dict["pub_types"]
        normalized_evidence_list = [pub_type_lookup[pubmed_label] for pubmed_label in pub_type_pubmed if pubmed_label in pub_type_lookup]
        categories = list(set([category for (pubmed_label, category, level) in normalized_evidence_list]))
        max_level_of_evidence = max([level for (pubmed_label, category, level) in normalized_evidence_list] + [-10])

        if max_level_of_evidence > 1:
            score += max_level_of_evidence * 1.0

        if "news and interest" in categories:
            score += 2

        if "English Abstract" in pub_type_pubmed:
            score += -5


    # these are more likely to use the word as an acronym rather than as the topic
    if my_dict["query_entities"]:
        for query_entity in my_dict["query_entities"]:
            article_title = my_dict.get("article_title")
            if not article_title:
                article_title = ""
            if u"({})".format(query_entity.upper()) in article_title:
                score = score * 0.25  # rather than making it go negative

    return score


class CachedEntityResponse(db.Model):
    __tablename__ = "cached_entity_response"
    entity_title = db.Column(db.Text, primary_key=True)
    collected = db.Column(db.DateTime)
    api_response = db.Column(JSONB)
    api_response_oa_only = db.Column(JSONB)

def get_cached_api_response(entity_title, oa_only):
    if oa_only:
        response = db.session.query(CachedEntityResponse.api_response_oa_only, CachedEntityResponse.collected).filter(CachedEntityResponse.entity_title==entity_title).first()
    else:
        response = db.session.query(CachedEntityResponse.api_response, CachedEntityResponse.collected).filter(CachedEntityResponse.entity_title==entity_title).first()
    return response


def fulltext_search_title(original_query, query_entities, oa_only, full=True):

    start_time = time()
    original_query_escaped = original_query.replace("'", "''")
    original_query_with_ands = ' & '.join(original_query_escaped.split(" "))
    query_to_use = u"({})".format(original_query_with_ands)


    if oa_only:
        oa_clause = u" and is_oa=True "
    else:
        oa_clause = " "

    dois = []
    rows = []
    # if "from_" in original_query and "to_" in original_query:
    #     print u"getting recent query"
    #     matches = re.findall("from_(\d{4}.\d{2}.\d{2})_to_(\d{4}.\d{2}.\d{2})", original_query)
    #     from_date = matches[0][0].replace("_", "-")
    #     to_date = matches[0][1].replace("_", "-")
    #     query_string = u"""
    #         select pmid, 0.05*COALESCE(num_events, 0.0)::float as rank
    #         from search_recent_hits_mv
    #         where published_date > :from_date ::timestamp and published_date < :to_date ::timestamp
    #         and num_events is not null
    #         {oa_clause}
    #         order by num_events desc
    #         limit 100 """.format(oa_clause=oa_clause)
    #     rows = db.engine.execute(sql.text(query_string), from_date=from_date, to_date=to_date).fetchall()
    #     print "done getting query getting pmids"

    if query_entities and len(query_entities)==1:
        query_entity = query_entities[0]
        query_entity = query_entity.replace("(", " ")
        query_entity = query_entity.replace(")", " ")
        query_entity = query_entity.replace("&", " ")

        print u"have query_entities"

        query_string = u"""
            select doi 
            from search_title_dandelion_simple_mv
            where title=:query_entity 
            and num_events >= 3
            {oa_clause}
            order by num_events desc 
            limit 120""".format(oa_clause=oa_clause)

        rows = db.engine.execute(sql.text(query_string), query_entity=query_entity).fetchall()
        print "done getting query getting dois"
        original_query_escaped = query_entity.replace("'", "''")
        original_query_with_ands = ' & '.join(original_query_escaped.split(" "))
        query_to_use = u"({})".format(original_query_with_ands)


    if rows:
        dois = [row[0] for row in rows]
        print "len dois", len(dois)

    # if len(dois) < 25:
    #     print "len(dois) < 25, in fulltext_search_title"

    if True: # debug
         print "doing full text search anyway"

        # need to do the full search
        print "len(dois) < 25, in fulltext_search_title"
        original_query_escaped = original_query.replace("'", "''")
        original_query_escaped = original_query_escaped.replace("&", "")
        original_query_escaped = original_query_escaped.replace("(", " ")
        original_query_escaped = original_query_escaped.replace(")", " ")
        original_query_with_ands = ' & '.join([w for w in original_query_escaped.split(" ") if w and w != " "])
        query_to_use = u"({})".format(original_query_with_ands)

        if query_entities:
            entities_escaped = []
            for query_entity in query_entities:
                print query_entity
                entity_escaped = query_entity
                entity_escaped = entity_escaped.replace("'", "''")
                entity_escaped = entity_escaped.replace("&", "")
                entity_escaped = entity_escaped.replace("(", "")
                entity_escaped = entity_escaped.replace(")", "")
                entity_escaped = u" & ".join(entity_escaped.split(u" "))
                entities_escaped += [entity_escaped]
                print "entities_escaped", entities_escaped
            entity_with_ands = u' & '.join(entities_escaped)
            print "entity_with_ands", entity_with_ands
            query_to_use += u" | ({})".format(entity_with_ands)

        # get ride of bad characters
        query_to_use = query_to_use.replace("!", "")

        print u"starting query for {}".format(query_to_use)

        query_string = u"""
            select
            doi,
            (ts_rank_cd(to_tsvector('english', article_title), to_tsquery(:query), 1) + 0.05*COALESCE(num_events,0.0)) AS rank
            FROM ricks_gtr_sort_results
            WHERE  
            to_tsvector('english', article_title) @@  to_tsquery(:query)
            and doi is not null 
            {oa_clause}
            order by rank desc
            limit 120;
            """.format(oa_clause=oa_clause)


        # print query_string


        rows = db.engine.execute(sql.text(query_string), query=query_to_use).fetchall()
        print "done getting query of sort data"

        # print rows
        dois = [row[0] for row in rows]

    time_for_dois = elapsed(start_time, 3)
    print u"done query for dois and sort data: got {} dois".format(len(dois))

    time_for_pubs_start_time = time()

    my_pubs_filtered = []
    if dois:
        if full:
            query_string = u"""
                select pmid,
                    doi,
                    article_title,
                    journal_title,
                    pub_types,
                    abstract_length,
                    is_oa,
                    num_events,
                    num_news_events,
                    (ts_rank_cd(to_tsvector('english', article_title), to_tsquery(:query), 1) + 0.05*COALESCE(num_events,0.0)) AS rank
                    from ricks_gtr_sort_results
                    where doi in ({dois_string})
                """.format(dois_string=u",".join([u"'{}'".format(str(d)) for d in dois]))
            # print query_string
            rows = db.engine.execute(sql.text(query_string), query=query_to_use, dois=dois).fetchall()
            print "done getting sort data"
            # print rows

            # print rows
            my_pubs_filtered = []
            for row in rows:
                my_dict = {
                    "pmid": row[0],
                    "doi": row[1],
                    "article_title": row[2],
                    "journal_title": row[3],
                    "pub_types": row[4],
                    "abstract_length": row[5],
                    "is_oa": row[6],
                    "num_events": row[7],
                    "num_news_events": row[8],
                    "score": row[9],
                    "query": query_to_use,
                    "query_entities": query_entities
                     }
                my_dict["adjusted_score"] = adjusted_score(my_dict)
                my_pubs_filtered.append(my_dict)

            # my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).options(orm.undefer_group('full')).all()
            # my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).\
            #     options(orm.raiseload(Pub.authors)).\
            #     options(orm.raiseload(Pub.dandelion_lookup)).\
            #     options(orm.raiseload(Pub.doi_lookup)).\
            #     all()
        else:
            my_pubs = db.session.query(Pub).filter(Pub.doi.in_(dois)).\
                options(orm.raiseload(Pub.authors)).\
                options(orm.raiseload(Pub.dandelion_lookup)).\
                options(orm.raiseload(Pub.doi_lookup)).\
                all()
            my_pubs_filtered = [p for p in my_pubs if not p.suppress]

    print "done query for my_pubs"


    time_for_pubs = elapsed(time_for_pubs_start_time, 3)

    return (my_pubs_filtered, time_for_dois, time_for_pubs)


def autocomplete_entity_titles(original_query):

    query_string = u"""
        select entity_title, sum_num_events, num_papers
        from search_autocomplete_dandelion_simple_mv
        where entity_title ilike :ilike_query
        and num_papers >= 25
        order by sum_num_events desc
        limit 10
        """.format(original_query=original_query)
    # print query_string
    rows = db.engine.execute(sql.text(query_string), ilike_query=u"{}%".format(original_query)).fetchall()
    print "done getting autocomplete query"

    # print rows
    entity_titles = []
    if rows:
        entity_titles = [row[0] for row in rows]

    return entity_titles
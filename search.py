from sqlalchemy import sql
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import JSONB
from time import time
import requests
import re

from app import db
from pub import Pub
from util import elapsed


class CachedEntityResponse(db.Model):
    __tablename__ = "cached_entity_response"
    entity_title = db.Column(db.Text, primary_key=True)
    collected = db.Column(db.DateTime)
    api_response = db.Column(JSONB)
    api_response_oa_only = db.Column(JSONB)

def get_cached_api_response(entity_title, oa_only):
    if oa_only:
        my_entity = db.session.query(CachedEntityResponse.api_response_oa_only).filter(CachedEntityResponse.entity_title==entity_title).first()
    else:
        my_entity = db.session.query(CachedEntityResponse.api_response).filter(CachedEntityResponse.entity_title==entity_title).first()
    return my_entity



def get_nerd_term_lookup(original_query):
    if not original_query:
        return

    clean_query = original_query.replace("'", "")
    url = u"http://nerd.huma-num.fr/nerd/service/kb/term/{}?lang=en".format(clean_query.title())
    r = requests.get(url)
    try:
        response_data = r.json()
        if not response_data.get("senses"):
            response_data = None
    except (ValueError, AttributeError):
        response_data = None

    return response_data


def fulltext_search_title(original_query, query_entities, oa_only, full=True):

    start_time = time()

    if oa_only:
        oa_clause = u" and is_oa=True "
    else:
        oa_clause = " "

    pmids = []
    rows = []
    if "from_" in original_query and "to_" in original_query:
        print u"getting recent query"
        matches = re.findall("from_(\d{4}.\d{2}.\d{2})_to_(\d{4}.\d{2}.\d{2})", original_query)
        from_date = matches[0][0].replace("_", "-")
        to_date = matches[0][1].replace("_", "-")
        query_string = u"""
            select pmid, 0.05*COALESCE(num_events, 0.0)::float as rank 
            from search_recent_hits_mv 
            where published_date > :from_date ::timestamp and published_date < :to_date ::timestamp   
            and num_events is not null
            {oa_clause}
            order by num_events desc 
            limit 100 """.format(oa_clause=oa_clause)
        rows = db.engine.execute(sql.text(query_string), from_date=from_date, to_date=to_date).fetchall()
        print "done getting query"

    elif query_entities and len(query_entities)==1:
        print u"have query_entities"
        query_string = u"""
            select pmid, 0.05*COALESCE(num_events, 0.0)::float as rank, doi, title, is_oa, num_events 
            from search_title_dandelion_mv
            where title=:query_entity 
            and num_events >= 3
            {oa_clause}
            order by num_events desc 
            limit 100""".format(oa_clause=oa_clause)
        rows = db.engine.execute(sql.text(query_string), query_entity=query_entities[0]).fetchall()
        print "done getting query"

    if rows:
        pmids = [row[0] for row in rows]
        print "len pmids", len(pmids)

    if len(pmids) < 25:
        # need to do the full search
        print "in fulltext_search_title"
        original_query_escaped = original_query.replace("'", "''")
        original_query_with_ands = ' & '.join(original_query_escaped.split(" "))
        query_to_use = u"({})".format(original_query_with_ands)

        if query_entities:
            entities_escaped = []
            for query_entity in query_entities:
                entity_escaped = query_entity.replace("'", "''")
                entities_escaped += entity_escaped.split(" ")
            entity_with_ands = u' & '.join(entities_escaped)
            query_to_use += u" | ({})".format(entity_with_ands)

        print u"starting query for {}".format(query_to_use)

        query_string = u"""
            select
            pmid, 
            (ts_rank_cd(to_tsvector('english', article_title), to_tsquery('{q}'), 1) + 0.05*COALESCE(num_events,0.0)) AS rank,
            article_title,
            num_events
            FROM search_titles_mv
            WHERE  
            to_tsvector('english', article_title) @@  to_tsquery('{q}')
            and doi is not null 
            {oa_clause}
            order by rank desc
            limit 100;
            """.format(q=query_to_use, oa_clause=oa_clause)
        # print query_string
        rows = db.engine.execute(sql.text(query_string)).fetchall()
        print "done getting query"

        # print rows
        pmids = [row[0] for row in rows]

    time_for_pmids = elapsed(start_time, 3)
    print u"done query for pmids: got {} pmids".format(len(pmids))

    time_for_pubs_start_time = time()

    if full:
        my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).options(orm.undefer_group('full')).all()
        # my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).\
        #     options(orm.raiseload(Pub.authors)).\
        #     options(orm.raiseload(Pub.dandelion_lookup)).\
        #     options(orm.raiseload(Pub.doi_lookup)).\
        #     all()
    else:
        my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).\
            options(orm.raiseload(Pub.authors)).\
            options(orm.raiseload(Pub.dandelion_lookup)).\
            options(orm.raiseload(Pub.doi_lookup)).\
            all()

    print "done query for my_pubs"

    for row in rows:
        my_id = row[0]
        for my_pub in my_pubs:
            if my_id == my_pub.pmid:
                my_pub.score = row[1]
    print "done filling out my_pub"

    my_pubs_filtered = [p for p in my_pubs if not p.suppress]
    time_for_pubs = elapsed(time_for_pubs_start_time, 3)

    return (my_pubs_filtered, time_for_pmids, time_for_pubs)


def autocomplete_entity_titles(original_query):

    query_string = u"""
        select entity_title, sum_num_events, num_papers
        from search_autocomplete_dandelion_mv
        where entity_title ilike '{original_query}%'
        and num_papers >= 25
        order by sum_num_events desc
        limit 10
        """.format(original_query=original_query)
    # print query_string
    rows = db.engine.execute(sql.text(query_string)).fetchall()
    print "done getting query"

    # print rows
    entity_titles = []
    if rows:
        entity_titles = [row[0] for row in rows]

    return entity_titles
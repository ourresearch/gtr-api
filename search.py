from sqlalchemy import sql
from sqlalchemy import orm
from time import time
import requests

from app import db
from pub import Pub
from util import elapsed

def get_synonym(original_query):
    clean_query = original_query.replace("'", "")
    # url = "http://wikisynonyms.ipeirotis.com/api/{}".format(clean_query.title())

    # try https://en.wikipedia.org/w/api.php?action=query&format=json&titles=diabetes&redirects=
    url = u"https://en.wikipedia.org/w/api.php?action=query&format=json&titles={}&redirects=".format(clean_query.title())
    headers = {"User-Agent": "team@impactstory.org"}

    r = requests.get(url, headers=headers)
    if r and r.status_code == 200:
        data = r.json()
        if "query" in data and "pages" in data["query"]:
            page = data["query"]["pages"].values()[0]
            synonym = page["title"]
            return synonym
        # if "terms" in data:
        #     best_term = data["terms"][0]
        #     if best_term["canonical"] == 1:
        #         synonym = best_term["term"]
        #         return synonym
    return None

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


def fulltext_search_title(original_query, synonym, oa_only, full=True):

    start_time = time()

    if oa_only:
        oa_clause = u" and is_oa=True "
    else:
        oa_clause = " "

    pmids = []
    rows = []
    if synonym:
        print u"have synonym"
        query_string = u"""
            select pmid, 0.05*COALESCE(num_events, 0.0)::float as rank, doi, title, is_oa, num_events 
            from search_title_dandelion_mv
            where title=:synonym 
            and num_events >= 3
            {oa_clause}
            order by num_events desc 
            limit 100""".format(oa_clause=oa_clause)
        # print query_string
        rows = db.engine.execute(sql.text(query_string), synonym=synonym).fetchall()
        print "done getting query"

        # print rows
        if rows:
            pmids = [row[0] for row in rows]
            print "len pmids", len(pmids)

    if len(pmids) < 25:
        # need to do the full search
        print "in fulltext_search_title"
        original_query_escaped = original_query.replace("'", "''")
        original_query_with_ands = ' & '.join(original_query_escaped.split(" "))
        query_to_use = u"({})".format(original_query_with_ands)

        if synonym:
            synonym_escaped = synonym.replace("'", "''")
            synonym_with_ands = ' & '.join(synonym_escaped.split(" "))
            query_to_use += u" | ({})".format(synonym_with_ands)

        print u"starting query for {}".format(query_to_use)

        query_string = u"""
            select
            pmid, 
            (ts_rank_cd(to_tsvector('english', article_title), to_tsquery('{q}'), 1) + 0.05*COALESCE(num_events,0.0)) AS rank,
            article_title,
            num_events
            FROM search_mv
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
    else:
        my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).\
            options(orm.raiseload(Pub.authors)).\
            options(orm.raiseload(Pub.unpaywall_lookup)).\
            options(orm.raiseload(Pub.dandelion_lookup)).\
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


def autcomplete_entity_titles(original_query):

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
from sqlalchemy import sql
from time import time
import requests

from app import db
from pub import Pub

def get_synonym(original_query):
    clean_query = original_query.replace("'", "")
    url = "http://wikisynonyms.ipeirotis.com/api/{}".format(clean_query.title())

    r = requests.get(url)
    if r and r.status_code == 200:
        data = r.json()
        if "terms" in data:
            best_term = data["terms"][0]
            if best_term["canonical"] == 1:
                synonym = best_term["term"]
                return synonym
    return None

def get_term_lookup(original_query):
    if not original_query:
        return

    clean_query = original_query.replace("'", "")
    url = u"http://nerd.huma-num.fr/nerd/service/kb/term/{}?lang=en".format(clean_query.title())
    r = requests.get(url)
    try:
        response_data = r.json()
    except ValueError:
        response_data = None

    if not response_data.get("senses"):
        response_data = None

    return response_data


def fulltext_search_title(original_query):

    print "in fulltext_search_title"
    original_query_escaped = original_query.replace("'", "''")
    original_query_with_ands = ' & '.join(original_query_escaped.split(" "))
    query_to_use = u"({})".format(original_query_with_ands)

    print "getting synonym"
    synonym = get_synonym(original_query)
    print "done getting synonym"
    if synonym:
        synonym_escaped = synonym.replace("'", "''")
        synonym_with_ands = ' & '.join(synonym_escaped.split(" "))
        query_to_use += u" | ({})".format(synonym_with_ands)

    print "starting query"
    query_string = u"""
        select
        medline_citation.pmid as pmid, 
        ts_headline('english', article_title, to_tsquery('{q}')) as snippet, 
        (ts_rank_cd(to_tsvector('english', article_title), to_tsquery('{q}'), 1) + 0.05*COALESCE(dois_with_ced_events.num_events,0)) AS rank,
        article_title,
        dois_with_ced_events.num_events
        FROM medline_citation, dois_pmid_lookup
        left join dois_with_ced_events on dois_pmid_lookup.doi=dois_with_ced_events.doi
        WHERE  
        to_tsvector('english', article_title) @@  to_tsquery('{q}')
        and (medline_citation.pmid)::text=dois_pmid_lookup.pmid
        order by rank desc
        limit 100;
        """.format(q=query_to_use)
    rows = db.engine.execute(sql.text(query_string)).fetchall()
    print "done getting query"
    # print rows
    pmids = [row[0] for row in rows]
    my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).all()
    print "done query for my_pubs"
    for row in rows:
        my_id = row[0]
        for my_pub in my_pubs:
            if my_id == my_pub.pmid:
                my_pub.snippet = row[1]
                my_pub.score = row[2]
    print "done filling out my_pub"
    return my_pubs

def autocomplete_phrases(query):
    query_string = ur"""
        with s as (SELECT id, lower(title) as lower_title FROM pub_2018 WHERE title iLIKE '%{query}%')
        select match, count(*) as score from (
            SELECT regexp_matches(lower_title, '({query}\w*?\M)', 'g') as match FROM s
            union all
            SELECT regexp_matches(lower_title, '({query}\w*?(?:\s+\w+){{1}})\M', 'g') as match FROM s
            union all
            SELECT regexp_matches(lower_title, '({query}\w*?(?:\s+\w+){{2}})\M', 'g') as match FROM s
            union all
            SELECT regexp_matches(lower_title, '({query}\w*?(?:\s+\w+){{3}}|)\M', 'g') as match FROM s
        ) s_all
        group by match
        order by score desc, length(match::text) asc
        LIMIT 50;""".format(query=query)

    rows = db.engine.execute(sql.text(query_string)).fetchall()
    phrases = [{"phrase":row[0][0], "score":row[1]} for row in rows if row[0][0]]
    return phrases
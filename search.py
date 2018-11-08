from sqlalchemy import sql
from time import time
import requests

from app import db
from pub import Pub

def get_synonym(original_query):
    url = "http://wikisynonyms.ipeirotis.com/api/{}".format(original_query.title())

    r = requests.get(url)
    if r and r.status_code == 200:
        data = r.json()
        if "terms" in data:
            best_term = data["terms"][0]
            if best_term["canonical"] == 1:
                synonym = best_term["term"]
                return synonym
    return None

def get_term_lookup(query):
    if not query:
        return

    url = u"http://nerd.huma-num.fr/nerd/service/kb/term/{}?lang=en".format(query)
    r = requests.get(url)
    try:
        response_data = r.json()
    except ValueError:
        response_data = None

    if not response_data.get("senses"):
        response_data = None

    return response_data


def fulltext_search_title(original_query):

    original_query_with_ands = ' & '.join(original_query.split(" "))
    query_to_use = u"({})".format(original_query_with_ands)

    synonym = get_synonym(original_query)
    if synonym:
        synonym_with_ands = ' & '.join(synonym.split(" "))
        query_to_use += u" | ({})".format(synonym_with_ands)

    query_string = """
        select
        medline_citation.pmid as pmid, 
        dois_pmid_lookup.doi,
        ts_headline('english', article_title, query) as snippet, 
        (ts_rank_cd(to_tsvector('english', article_title), query, 1) + 0.05*COALESCE(dois_with_ced_events.num_events,0)) AS rank,
        article_title,
        dois_with_ced_events.num_events,
        pub_date_year,
        is_oa,
        best_host,
        best_version,
        oa_url
        FROM medline_citation, to_tsquery('english', '{}') query, dois_pmid_lookup
        left join dois_with_ced_events on dois_pmid_lookup.doi=dois_with_ced_events.doi
        join unpaywall_api_response_view on unpaywall_api_response_view.id=dois_with_ced_events.doi
        WHERE 
        to_tsvector('english', article_title) @@ query
        and abstract_text is not null and abstract_text != 'N/A' and length(abstract_text) > 2
        and (medline_citation.pmid)::text=dois_pmid_lookup.pmid
        ORDER BY rank DESC
        LIMIT 100;
        ;""".format(query_to_use)
    rows = db.engine.execute(sql.text(query_string)).fetchall()
    # print rows
    pmids = [row[0] for row in rows]
    my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).all()
    for row in rows:
        my_id = row[0]
        for my_pub in my_pubs:
            if my_id == my_pub.pmid:
                my_pub.doi_url = u"https://doi.org/{}".format(row[1])  # fix, just use doi instead
                my_pub.snippet = row[2]
                my_pub.score = row[3]
                my_pub.is_oa = row[7]
                my_pub.best_host = row[8]
                my_pub.best_version = row[9]
                my_pub.oa_url = row[10]
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
from sqlalchemy import sql
from time import time

from app import db
from pub import Pub

def fulltext_search_title(query):
    # query_string = """
    #   SELECT id, ts_headline('english', title, query), ts_rank_cd(to_tsvector('english', title), query, 32) AS rank
    #     FROM pub_2018, plainto_tsquery('english', '{}') query  -- or try plainto_tsquery, phraseto_tsquery, to_tsquery
    #     WHERE to_tsvector('english', title) @@ query
    #     ORDER BY rank DESC
    #     LIMIT 50;""".format(query)

# select
# medline_citation.pmid,
# dois_pmid_lookup.doi_url,
# article_title,
# to_tsvector('english', COALESCE(article_title,'')),
# -- num_events,
# pub_date_year
# -- , mesh
# from dois_pmid_lookup, medline_citation
# -- left outer join dois_with_ced_events on dois_pmid_lookup.doi=dois_with_ced_events.doi
# where (medline_citation.pmid)::text=dois_pmid_lookup.pmid
# and doi_url is not null and doi_url != ''
# limit 10


    query_string = """
        SELECT
        medline_citation.pmid as pmid, 
        dois_pmid_lookup.doi_url,
        ts_headline('english', article_title, query) as snippet, 
        ts_rank_cd(to_tsvector('english', article_title), query, 1) AS rank,
        article_title,
        pub_date_year
        FROM medline_citation, dois_pmid_lookup, plainto_tsquery('english', '{}') query  -- or try plainto_tsquery, phraseto_tsquery, to_tsquery
        WHERE to_tsvector('english', article_title) @@ query
        and abstract_text is not null and abstract_text != 'N/A' and length(abstract_text) > 2
        and (medline_citation.pmid)::text=dois_pmid_lookup.pmid
        ORDER BY rank DESC
        LIMIT 20;""".format(query)
    rows = db.engine.execute(sql.text(query_string)).fetchall()
    # print rows
    pmids = [row[0] for row in rows]
    my_pubs = db.session.query(Pub).filter(Pub.pmid.in_(pmids)).all()
    for row in rows:
        my_id = row[0]
        for my_pub in my_pubs:
            if my_id == my_pub.pmid:
                my_pub.doi_url = row[1]
                my_pub.snippet = row[2]
                my_pub.score = row[3]
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
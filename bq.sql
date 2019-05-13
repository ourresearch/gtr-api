create table bq_pubmed_doi_unpaywall (
doi text,
pmid text,
pmcid text,
is_oa boolean,
best_host_type text,
best_version text,
oa_url text)


create materialized view search_titles_mv as (
 SELECT medline_citation.pmid,
 	lookup.doi,
    medline_citation.article_title,
    events.num_events,
    is_oa
   FROM medline_citation
     LEFT JOIN bq_pubmed_doi_unpaywall lookup ON medline_citation.pmid = lookup.pmid
     LEFT JOIN local_dois_with_ced_events_mv events ON lookup.doi = events.doi
     );


CREATE INDEX search_titles_mv_title_gin_trgm_idx ON search_titles_mv USING gin (article_title gin_trgm_ops);
create index search_titles_mv_title_gin_tsvector_idx on search_titles_mv using gin(to_tsvector('english', article_title))
CREATE INDEX search_titles_mv_doi_idx ON search_titles_mv (doi)
CREATE INDEX search_titles_mv_is_oa_num_events_idx ON search_titles_mv (is_oa, num_events)
vacuum analyze search_titles_mv



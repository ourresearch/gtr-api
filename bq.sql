create table bq_pubmed_doi_unpaywall (
doi text,
pmid text,
pmcid text,
is_oa boolean,
best_host_type text,
best_version text,
oa_url text)


create materialized view search_mv as (
 SELECT medline_citation.pmid,
 	lookup.doi,
    medline_citation.article_title,
    dois_with_ced_events.num_events,
    is_oa
   FROM medline_citation
     LEFT JOIN dois_pmid_lookup_pmid_numeric_mv lookup ON medline_citation.pmid::numeric = lookup.pmid_numeric
     LEFT JOIN dois_with_ced_events ON lookup.doi = dois_with_ced_events.doi
     LEFT JOIN bq_pubmed_doi_unpaywall ON lookup.doi = bq_pubmed_doi_unpaywall.doi
     );

CREATE INDEX search_mv_title_gin_trgm_idx ON search_mv USING gin (article_title gin_trgm_ops);
create index search_mv_title_gin_tsvector_idx on search_mv using gin(to_tsvector('english', article_title))

VACUUM ANALYZE search_mv

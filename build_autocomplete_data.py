#!/usr/local/bin/python
# -*- coding: utf-8 -*-

from sqlalchemy import sql
import json

from app import db

# refresh materialized view first:
# refresh materialized view search_autocomplete_dandelion_mv

query_string = u"""
    select entity_title, sum_num_events, num_papers
    from search_autocomplete_dandelion_mv
    where num_papers >= 25
    order by sum_num_events desc
    """
# print query_string
rows = db.engine.execute(sql.text(query_string)).fetchall()
print "done getting query"


entity_titles = [row[0] for row in rows]
print "number entities: {}".format(len(entity_titles))

ordered_autocomplete_dicts = [
    {"lower": e.lower(), "value": e} for e in entity_titles if e
]

f = open("/Users/hpiwowar/Dropbox/ti/data/gtr_autocomplete.json", "w")
f.writelines(json.dumps(ordered_autocomplete_dicts, indent=4))
f.close()

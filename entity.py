#!/usr/local/bin/python
# -*- coding: utf-8 -*-

# based on nltk's stop word list here https://gist.github.com/sebleier/554280
# then with some custom ones added

import requests
import os
import inflect

from pub import call_dandelion
from annotation_list import AnnotationList
from search import autocomplete_entity_titles

inflect_engine = inflect.engine()


stop_words = """
cause
caused
good
benefit
take
harm
healthy
help
evidence
best
worst
i
me
my
myself
we
our
ours
ourselves
you
your
yours
yourself
yourselves
he
him
his
himself
she
her
hers
herself
it
its
itself
they
them
their
theirs
themselves
what
which
who
whom
this
that
these
those
am
is
are
was
were
be
been
being
have
has
had
having
do
does
did
doing
a
an
the
and
but
if
or
because
as
until
while
at
by
for
with
about
against
between
into
through
during
before
after
above
below
to
from
up
down
in
out
on
off
over
under
again
further
then
once
here
there
when
where
why
how
all
any
both
each
few
more
most
other
some
such
no
nor
not
only
own
same
so
than
too
very
s
t
can
will
just
don
should
now""".split("\n")

# removed
# of  #quality of life is good


def get_entities_from_query(query):

    query_lower = query.lower()

    for a in autocomplete_entity_titles(query):
        if a.lower() == query_lower:
            return [a]

    query_singular = inflect_engine.singular_noun(query)
    if query_singular and (query_singular != query_lower):
        query_singular_lower = query_singular.lower()
        for a in autocomplete_entity_titles(query_singular):
            if a.lower() == query_singular_lower:
                return [a]

    api_key = os.getenv("DANDELION_API_KEY_QUERY_PARSING")

    # from https://stackoverflow.com/a/5486509/596939
    query_no_stopwords_list = []
    for word in query.split(u" "): # iterate over word_list
        if word not in stop_words:
            query_no_stopwords_list.append(word)
    query_no_stopwords = u" ".join(query_no_stopwords_list)

    dandelion_results = call_dandelion(query_no_stopwords, api_key=api_key, label_top_entities=False)
    my_annotation_list = AnnotationList(dandelion_results)
    annotation_titles = [anno.title for anno in my_annotation_list.list()]
    return annotation_titles
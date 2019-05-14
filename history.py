import shortuuid
import datetime

from app import db
from util import safe_commit

def log_query(query, ip):
    my_log = QueryHistory(query=query, ip=ip)
    db.session.add(my_log)
    safe_commit(db)

class QueryHistory(db.Model):
    __tablename__ = "query_history"
    id = db.Column(db.Text, primary_key=True)
    query = db.Column(db.Text)
    ip = db.Column(db.Text)
    created = db.Column(db.DateTime)

    def __init__(self, **kwargs):
        self.id = shortuuid.uuid()[0:20]
        self.created = datetime.datetime.utcnow().isoformat()
        super(QueryHistory, self).__init__(**kwargs)


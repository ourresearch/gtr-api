import shortuuid
import datetime

from app import db
from util import safe_commit

def notification_signup(email, query):
    my_signup = NotificationSignups(email=email, query=query)
    db.session.add(my_signup)
    safe_commit(db)

class NotificationSignups(db.Model):
    __tablename__ = "notification_signups"
    id = db.Column(db.Text, primary_key=True)
    email = db.Column(db.Text)
    query = db.Column(db.Text)
    created = db.Column(db.DateTime)

    def __init__(self, **kwargs):
        self.id = shortuuid.uuid()[0:20]
        self.created = datetime.datetime.utcnow().isoformat()
        super(NotificationSignups, self).__init__(**kwargs)


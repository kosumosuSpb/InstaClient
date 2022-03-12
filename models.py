from datetime import datetime
from pony.orm import *


db = Database()

db.bind(provider='sqlite', filename='db.sqlite', create_db=True)


class User(db.Entity):
    id = PrimaryKey(int, auto=True)
    username = Optional(str)
    full_name = Optional(str)
    is_private = Optional(bool)
    is_verified = Optional(bool)
    follower_count = Optional(int)
    following_count = Optional(int)
    public_email = Optional(str)
    contact_phone_number = Optional(str)
    media_count = Optional(int)
    biography = Optional(str)
    is_business = Optional(bool)
    external_url = Optional(str)
    upd_datetime = Required(datetime, default=lambda: datetime.utcnow())
    relationships_snaps = Set('RelationshipsSnap', reverse='owner')
    in_followers_snaps = Set('RelationshipsSnap', reverse='followers')
    in_following_snaps = Set('RelationshipsSnap', reverse='followings')


class RelationshipsSnap(db.Entity):
    id = PrimaryKey(int, auto=True)
    date_time = Required(datetime, unique=True, default=lambda: datetime.utcnow())
    owner = Required(User, reverse='relationships_snaps')
    followers = Set(User, reverse='in_followers_snaps')
    followings = Set(User, reverse='in_following_snaps')


db.generate_mapping(create_tables=True)

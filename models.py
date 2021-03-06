from datetime import datetime
from config import DB_SETTINGS
from pony.orm import *
import sqlite3


db = Database()

db.bind(**DB_SETTINGS)


class User(db.Entity):
    id = PrimaryKey(int, auto=True, size=64)
    username = Optional(str)
    last_username = Optional(str)
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
    is_deleted = Optional(bool)

    @property
    def followers(self):
        """Возвращает подписчиков из последнего снапа"""
        # берём самый новый снап
        last_snap = self.relationships_snaps.select(lambda rs: rs.followers).order_by(lambda rs: desc(rs.date_time)).first()
        return last_snap.followers.select().fetch() if last_snap else None

    @property
    def followings(self):
        """Возвращает подписки из последнего снапа"""
        # берём самый новый снап
        last_snap = self.relationships_snaps.select(lambda rs: rs.followings).order_by(lambda rs: desc(rs.date_time)).first()
        return last_snap.followings.select().fetch() if last_snap else None

    def before_update(self):
        """Сохраняет в отдельное поле старый юзернейм, если он изменился в обновлении"""
        prev_username = self._dbvals_.get(User.username)
        new_username = self.username
        if prev_username != new_username:
            self.last_username = prev_username

    def __repr__(self):
        return f'User[{self.id}: {self.username}]'


class RelationshipsSnap(db.Entity):
    id = PrimaryKey(int, auto=True)
    date_time = Required(datetime, unique=True, default=lambda: datetime.utcnow())
    owner = Required(User, reverse='relationships_snaps')
    followers = Set(User, reverse='in_followers_snaps')
    followings = Set(User, reverse='in_following_snaps')


db.generate_mapping(create_tables=True)


class DBChanges:
    """Костыль для Pony ORM, позволяющий добавлять и удалять колонки в таблицах, т.к. в ней нет миграций"""
    def __init__(self, db_name: str):
        self.db = db_name
        self.conn = sqlite3.connect(self.db)
        # self.conn = sqlite3.connect(:memory:)  # если БД в памяти

    def add_columns(self, table: str, column: str, col_type, default, null: bool, db_type='sqLite'):
        """Добавление колонки в таблицу"""
        cur = self.conn.cursor()
        cur.execute(f"ALTER TABLE {table} ADD column {column} {col_type} DEFAULT {default}")
        self.conn.commit()

    def delete_columns(self, table, column):
        """Удаление колонки из таблицы"""
        pass


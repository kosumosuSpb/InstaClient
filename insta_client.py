"""
Обёртка для instagrapi, сделана для расширения функционала,
например, отслеживания того, кто подписался и отписался за какой-то период.

Всё кое-как описано в README.md

REMINDER:
если обратиться к
https://www.instagram.com/{username}/?__a=1

то получаешь json с полной инфой по пользователю, но с огромным количеством мусора

маниакально старался не использовать re, но возможно, что зря
"""

from instagrapi import Client, exceptions
from config import INST_LOGIN, INST_PASS, PROXY
from datetime import datetime  # импортируется вместе с моделями
from pony.orm import desc  # импортируется вместе с моделями
from pony.orm.core import ObjectNotFound  # импортируется вместе с моделями
import requests
from models import *
import logging
import os


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
logger = logging.getLogger('InstaClient')


class InstaClient(Client):
    def __init__(self, *args, update=False, **kwargs):
        super().__init__(**kwargs)
        self.update = update

    FIELDS = (
        'username',
        'full_name',
        'is_private',
        'is_verified',
        'biography',
        'is_business',
        'follower_count',
        'following_count',
        'public_email',
        'contact_phone_number',
        'external_url',
    )

    @staticmethod
    def create_and_login(login=INST_LOGIN, password=INST_PASS, proxy=None):
        """Возвращает залогиненый объект класса"""
        instance = InstaClient()

        if proxy:
            instance.set_proxy(proxy)

        if instance.login(login, password):
            # Если логин прошёл успешно, то пишем в лог про это и возвращаем объект
            logger.info(f'Пользователь {login} авторизован успешно. Имя пользователя - {instance.username}')
            return instance
        else:
            logger.info(f'Авторизовать пользователя {login} не удалось')

    def _get_correct_user_id(self, user):
        """Получает пользователя, возвращает его id"""
        # если не указан логин, то берём логин из объекта
        if not user:
            # проверка авторизованности
            if self.username:
                logger.info(f'Не указан пользователь, берём его из объекта...')
                user_id = self.user_id
            # если не авторизован, то кидаем исключение
            else:
                logger.warning('Не указан пользователь и не выполнена авторизация!')
                raise exceptions.ClientLoginRequired('Надо залогиниться!')

        # если указан id
        elif (isinstance(user, str) and user.isdigit()) or isinstance(user, int):
            logger.debug('Указан user_id, используем его')
            user_id = user

        # если указан юзернейм, надо получить id
        else:
            try:
                logger.info(f'Получаем id пользователя {user}...')
                db_user = User.get(username=user)
                user_id = db_user.id if db_user else self.user_id_from_username(user)
            except exceptions.ClientError:
                logger.error(f'Ошибка! Что-то с запросом. Возможно, не верно указан пользователь: {user}')
                raise
        return user_id

    @db_session
    def create_user_model(self, usershort: dict) -> User:
        """Фильтрует UserShort, создаёт экземпляр пользователя, сохраняет в БД и возвращает его"""
        # если пришёл не словарь, то пытаемся сделать из него словарь
        if not isinstance(usershort, dict):
            try:
                logger.warning('Должен был придти словарь, а пришло что-то другое! Пытаемся сделать словарь...')
                usershort = usershort.__dict__
            except Exception as e:
                logger.error('Не удалось сделать словарь!')
                logger.error(f'Ошибка! Подробности: {e}')
                raise

        user_id = int(usershort['pk'])
        user = User.get(id=user_id)

        if user:
            logger.debug(f'Пользователь найден в БД')

            # если установлен флаг update, то обновляем пользователя
            if self.update:
                logger.debug('Установлен флаг update, обновляем пользователя в БД...')
                usershort = {key: val for key, val in usershort.items() if key in self.FIELDS and val}
                user.set(**usershort)
            return user

        else:
            logger.debug(f'Пользователь в БД не найден, создаём его...')
            # фильтруем UserShort, т.к. нам нужны не все поля
            logger.debug(f'Фильтруем атрибуты пользователя {user_id}')
            usershort = {key: val for key, val in usershort.items() if key in self.FIELDS and val}

            # создаём пользователя в БД
            user = User(id=user_id, **usershort)
            logger.debug(f'Пользователь {user} создан')
            return user

    def users_to_db(self, usershorts: list) -> set:
        """
        Сохранение юзеров в БД и возврат сета юзеров

        Принимает формат: [UserShort( ... ), ]

        :param usershorts: Список [UserShort( ... ), ]
        :return: множество с пользователями
        """
        users_set = set()

        for usershort in usershorts:
            user = self.create_user_model(usershort.dict())
            users_set.add(user.id)  # сохраняем id, потому что пони не умеет передавать объекты в разных db_session

        return users_set

    @db_session
    def update_user(self, user, fullinfo=False):
        """Обновление пользователя в БД"""
        user_id = int(self._get_correct_user_id(user))

        # получаем пользователя из БД
        db_user = User.get(id=user_id)

        # получаем инфу пользователя у инсты
        # придёт или User или UserShort
        upd_user = self.user_short_gql(user_id) if not fullinfo else self.user_info(user_id)
        upd_user = upd_user.__dict__

        # обновляем пользователя в БД
        upd_user = {key: val for key, val in upd_user.items() if key in self.FIELDS and val}
        db_user.set(**upd_user)

    def get_userinfo(self, user: str) -> dict:
        """
        Простой публичный способ получения инфы юзера

        может не работать, поэтому лучше использовать user_info

        """
        username = user if isinstance(user, str) and not user.isdigit() else self.username_from_user_id(user)
        response = requests.get(f'https://www.instagram.com/{username}/?__a=1')
        userinfo = response.json()['graphql']['user']
        pk = userinfo['id']
        userinfo = {key: val for key, val in userinfo.items() if key in self.FIELDS and val}
        userinfo['id'] = int(pk)
        return userinfo

    @db_session
    def make_relations_snap(self, snap_owner, users_set1, users_set2=None, relation_type='followers'):
        """
        Создание снимка связей пользователя snap_owner

        Принимает владельца снимка, сет из пользователей и тип связи

        По-умолчанию добавляются подписчики

        :param snap_owner: владелец снимка (чьи это подписчики/подписки)
        :param users_set1: список пользователей
        :param users_set2: список пользователей 2 (на случай, если добавляются сразу и подписчики и подписки)
                           сначала подписчики, потом подписки
        :param relation_type: возможные варианты: 'followers', 'following', 'all'
        :return:
        """
        snap_owner = int(self._get_correct_user_id(snap_owner))
        logger.info(f'Пользователь id = {snap_owner}. Достаём его из БД или создаём...')

        # ищем в базе по id пользователя, для которого создаётся снап
        # если его не существует, то создаём его
        snap_owner = User.get(id=snap_owner) or self.get_user_and_create(snap_owner)

        # достаём пользователей из БД по id
        users_set1 = {User[user_id] for user_id in users_set1}

        # если добавляем сразу и подписчиков и подписки, то
        users_set2 = {User[user_id] for user_id in users_set2} if users_set2 else None

        return (
            RelationshipsSnap(owner=snap_owner, followers=users_set1) if relation_type == 'followers' else
            RelationshipsSnap(owner=snap_owner, followings=users_set1) if relation_type == 'followings' else
            RelationshipsSnap(owner=snap_owner, followers=users_set1, followings=users_set2) if relation_type == 'all'
            else None
        )

    def get_user_and_create(self, user):
        """Принимает юзернейм, запрашивает инфу, создаёт юзера в БД"""
        user = self._get_correct_user_id(user)
        logger.info('Создаём пользователя: забираем инфу из инсты...')
        user = self.user_info(user)  # user_info хочет str, но может принять и int, т.к. конвертит на входе стразу в str
        logger.info('Создаём пользователя: сохраняем в БД...')
        user = self.create_user_model(int(user.pk), user.__dict__)
        return user

    def save_followers(self, user=None, mode='db', update=False):
        """Сохранение id подписчиков в файл"""
        user_id = self._get_correct_user_id(user)

        # обновлять пользователей в БД?
        self.update = update

        # получаем список подписчиков
        # придёт список с инфой о подписчиках вида
        # [UserShort(pk='123456789', username='user_name', full_name='Имя', ... ), ... ]
        logger.info(f'Получаем подписчиков пользователя {user}...')
        followers = self.user_followers_v1(user_id)
        logger.info(f'Получено {len(followers)} подписчиков')

        if not followers:
            logger.info('Нечего сохранять, завершаем работу...')
            # тут надо логику пересмотреть
            if not self.username:
                logger.warning('Логин не выполнен, поэтому нельзя было получить подписчиков!')
            return

        if mode == 'txt':
            logger.info('Сохраняем подписчиков пользователя в txt...')
            followers_snap = self.snap_to_txt(user, followers, relation_type='followers')
            logger.info(f'Снимок сохранён в файл {followers_snap}')
        elif mode == 'db':
            logger.info('Сохраняем подписчиков пользователя в БД...')
            users_id = self.users_to_db(followers)

            logger.info('Создаём снимок подписчиков...')
            followers_snap = self.make_relations_snap(snap_owner=user_id, users_set1=users_id, relation_type='followers')
            logger.info(f'Снимок сохранён, id = {followers_snap.id}')

    def save_followings(self, user=None, mode='db', update=False):
        """Сохранение подписок"""
        user_id = self._get_correct_user_id(user)

        logger.info(f'Получаем подписки пользователя {user}...')
        followings = self.user_following_v1(user_id)
        logger.info(f'Получено {len(followings)} подписок, сохраняем...')

        if not followings:
            logger.info('Нечего сохранять')
            return

        if mode == 'db':
            logger.info('Сохраняем подписки пользователя в БД...')
            users_id = self.users_to_db(followings)

            logger.info('Создаём снимок подписок...')
            followings_snap = self.make_relations_snap(snap_owner=user_id, users_set1=users_id,
                                                       relation_type='followings')
            logger.info(f'Снимок сохранён, id = {followings_snap.id}')
        elif mode == 'txt':
            pass
        else:
            pass

    @staticmethod
    def snap_to_txt(user, users, relation_type='followers'):
        """Сохранение снапа в txt"""
        if relation_type not in ('followers', 'followings'):
            logger.warning(f'Неправильно указан relation_type! Должен быть либо followers, либо followings! '
                           f'Указан - {relation_type}')
            raise AttributeError('Неправильно указан relation_type!')

        # проверяем наличие папки под файлы, если нету - создаём
        if not os.path.isdir('inst'):
            logger.info('Не нашли папку inst, создаём...')
            os.mkdir('inst')

        # записываем в файл
        # сохраняем только ключи, так что у нас останутся только id пользователей
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        counter = 0
        filename = f'{user}_{relation_type}_{now}.txt'
        with open(f'inst/{filename}', 'w+') as f:
            for s in users:
                s = s.pk
                f.write(s+'\n')
                counter += 1

        logger.info(f'Сохранено {counter} пользователей')

        return filename

    @db_session
    def followers_changes_db(self, user, show_id=False):
        """Сравнить два последних снапа подписчиков в БД и показать разницу"""
        user_id = self._get_correct_user_id(user)
        try:
            user = User[user_id]
        except ObjectNotFound:
            logger.warning(f'Пользователь {user} не найден в БД!')
            raise ObjectNotFound(f'Пользователь {user} не найден в БД!')

        # отсортируем снапы, в которых есть подписчики по дате и возьмём первые два - самые новые
        query = RelationshipsSnap.select(
            lambda rs: rs.followers and rs.owner == user
        ).order_by(
            lambda rs: desc(rs.date_time)
        )[:2]

        if len(query) == 2:
            snap_new, snap_old = query
        else:
            logger.warning('Снапов меньше двух, нечего сравнивать!')
            return

        # вытаскиваем из снапов подписчиков
        old_followers = snap_old.followers.select().fetch()
        new_followers = snap_new.followers.select().fetch()

        # получаем разницу
        difference = set(new_followers).symmetric_difference(old_followers)

        if not difference:
            logger.info('Изменений в подписчиках нет')
            return

        # эти - подписались (потому что их нет в старом снапе)
        # срез с -1 потому что в конце у нас перевод строки остался
        new = [follower.username for follower in difference if follower not in old_followers]

        # эти - отписались (потому что их нет в новом)
        gone = [follower.username for follower in difference if follower not in new_followers]

        logger.info(f'\nПодписались: {", ".join(str(s) for s in new)}\n'
                    f'Отписались: {", ".join(str(s) for s in gone)}')

        return {
            'Подписались': new,
            'Отписались': gone
        }

    def followers_changes_txt(self, user, show_id=False):
        """Сравнить последний и предпоследний файлы и показать разницу"""
        # получаем список файлов в папке inst
        files = os.listdir(path="./inst")
        logger.debug(f'Файлы: {files}')

        files = sorted([file for file in files if file[:len(user)] == user])  # берём только нужный юзернейм и сортируем

        if len(files) < 2:
            logger.info('Нечего сравнивать, файлов меньше двух')
            return

        f2, f1 = files[-2:]  # берём последние два - самые поздние

        # читаем оба файла. Получим два списка вида ['49520889582\n', '51507879495\n', '50037477495\n', ... ]
        # перевод строки потом надо не забыть убрать. Сразу не убираю, чтобы лишнюю работу не делать
        logger.info(f'Открываем два последних файла: {f2}, {f1}')
        with open(f'inst/{f2}') as file2, open(f'inst/{f1}') as file1:
            f2 = file2.readlines()
            f1 = file1.readlines()

        # находим разницу в файлах
        difference = set(f1).symmetric_difference(f2)
        logger.debug(f'Получившееся множество: {difference}')

        if not difference:
            print('Изменений в подписчиках нет')
            return

        # эти - подписались (потому что их нет в старом файле)
        # срез с -1 потому что в конце у нас перевод строки остался
        new = [follower[:-1] for follower in difference if follower not in f2]
        new = self.get_usernames(new) if not show_id else new

        # эти - отписались (потому что их нет в новом)
        gone = [follower[:-1] for follower in difference if follower not in f1]
        gone = self.get_usernames(gone) if not show_id else gone

        logger.info(f'\nПодписались: {", ".join(str(s) for s in new)}\n'
                    f'Отписались: {", ".join(str(s) for s in gone)}')

        return {
            'Подписались': new,
            'Отписались': gone
        }

    @db_session
    def followings_changes_db(self, user, show_id=False):
        """Сравнить два последних снапа подписок в БД и показать разницу"""
        user_id = self._get_correct_user_id(user)
        try:
            user = User[user_id]
        except ObjectNotFound:
            logger.warning(f'Пользователь {user} не найден в БД!')
            raise ObjectNotFound(f'Пользователь {user} не найден в БД!')

        # отсортируем снапы, в которых есть подписки по дате и возьмём первые два - самые новые
        query = RelationshipsSnap.select(
            lambda rs: rs.followings and rs.owner == user
        ).order_by(
            lambda rs: desc(rs.date_time)
        )[:2]

        if len(query) == 2:
            snap_new, snap_old = query
        else:
            logger.warning('Снапов меньше двух, нечего сравнивать!')
            return

        # вытаскиваем из снапов подписчиков
        old_followings = snap_old.followings.select().fetch()
        new_followings = snap_new.followings.select().fetch()

        # получаем разницу
        difference = set(new_followings).symmetric_difference(old_followings)

        if not difference:
            logger.info('Изменений в подписках нет')
            return

        # на эти юзер подписался (потому что их нет в старом снапе)
        new = [following.username for following in difference if following not in old_followings]

        # а от этих отписался, сам или его отписали (потому что их нет в новом)
        gone = [following.username for following in difference if following not in new_followings]

        logger.info(f'\nПодписался на: {", ".join(str(s) for s in new)}\n'
                    f'Отписался от: {", ".join(str(s) for s in gone)}')

        return {
            'Подписался на': new,
            'Отписался от': gone
        }

    def get_usernames(self, user_ids: list) -> list:
        """Принимает список id, возвращает список юзернеймов"""
        usernames = []

        for user_id in user_ids:
            try:
                usernames.append(self.username_from_user_id(user_id))
            except Exception as e:
                logger.warning(f'Пользователь {user_id} не найден! Вероятно, он был удалён')
                logger.error(f'Ошибка! {e}')
                usernames.append(f'ErrGetUsr({user_id})')
        return usernames

    def take_file_dump(self):
        """Принимает файл дампа подписчиков"""

    def find_mutual_followers(self, user1, user2, using_db=True):
        """Находит общих подписчиков между двумя пользователями"""

    def txt_to_db_snap(self, user: str, file: str = 'last', relation_type: str = 'followers'):
        """
        Экспортирует txt снимок в БД

        по-умолчанию указывается только юзер, а метод берёт последний файл подписчиков

        :param user: пользователь для которого сохраняется снап
        :param file: название файла (или 'last' - если последний)
        :param relation_type: followers или followings
        :return:
        """
        logger.info('Начинаем экспорт из txt в БД...')
        logger.info(f'Начальные условия: файл: {file}, user: {user}, тип связи: {relation_type}')

        if relation_type not in ('followers', 'followings'):
            logger.error('Не правильно указан relation_type!')
            raise AttributeError('Не правильно указан relation_type!')

        if file == 'last':
            # получаем список файлов в папке inst
            files = os.listdir(path="./inst")
            files = sorted([file for file in files
                            if file[:len(user)] == user and relation_type in file])  # берём только нужный юзернейм и сортируем
            file = files[-1]  # берём последний в списке, он же последний по дате (т.к. в имени файла содержится дата)
        else:
            # костыль, чтобы не конфликтовало с тем, что в имени файла
            # всё-таки надо использовать re...
            end = file.index('_')
            user = file[:end]
            relation_type = file[len(user) + 1:-24]

            logger.info(f'Изменённые условия: файл: {file}, user: {user}, тип связи: {relation_type}')

        # открываем файл, считываем его, удаляем лишние переводы строк
        logger.info(f'Открываем файл {file}...')
        with open(f'inst/{file}') as f:
            users = f.readlines()
            users = [s[:-1] for s in users]  # удаляем перевод строки в каждом считанном id

        users_dict = {}

        logger.info(f'Собрано {len(users)} id пользователей')
        logger.info('Запрашиваем инфу о пользователях...')
        # запрашиваем UserShorts, собираем словарь вида:
        # {'987654321': UserShort(pk='123456789', username='user_name', full_name='Имя', ... ), ... }
        # можно вместо user_short_gql использовать user_info, но объём данных будет больше
        # и процесс будет медленнее
        for user_id in users:
            try:
                usershort = self.user_short_gql(user_id)  # быстро перестаёт получать инфу и даёт её очень мало
                # usershort = self.user_info(user_id)  # очень медленно
            except exceptions.ClientError as e:
                logger.error(f'Ошибка! Не удалось получить пользователя {user_id}')
                logger.error(f'Подробности: {e}')
                usershort = None

            users_dict[user_id] = usershort

        # сохраняем юзеров в БД, получаем обратно сет с ними
        # чтобы сохранить в снап
        logger.info('Сохраняем пользователей в БД...')
        users_set = self.users_to_db(users_dict)

        # вытаскиваем из имени файла дату его создания
        logger.info('Вытаскиваем дату создания txt...')
        date_time = file[-23:-4]
        date_time = datetime.strptime(date_time, '%Y-%m-%d_%H-%M-%S')

        logger.info(f'Проверяем, есть ли пользователь {user} в БД...')
        # получаем id пользователя
        snap_owner = self._get_correct_user_id(user)

        # проверяем, есть ли он в БД, если его нет создаём
        if not User.get(snap_owner):
            logger.info(f'Пользователя {user} в БД нет, создаём...')
            usershort = self.user_short_gql(snap_owner)
            self.create_user_model(snap_owner, usershort.__dict__)

        # сохраняем снап в БД
        logger.info('Сохраняем снап в БД...')
        snap = self.make_relations_snap(
            owner=snap_owner,
            users_set1=users_set,
            users_set2=None,
            relation_type=relation_type,
            date_time=date_time
        )

        logger.info(f'Снап из файла {file} в БД сохранён успешно! ID = {snap.id}')


logger.info('Hi, InstaClient here')

"""
Обёртка для instagrapi, сделана для расширения функционала, 
например, отслеживания того, кто подписался и отписался за какой-то период.
В перспективе должен отслеживать любые изменения указанного профиля (если он не закрыт)

название ещё не придумал:
InstaClient - рабочее
InstaGrappa ?
InstaGrappi -
InstagrYappi -
Instalker -
InstSpector
InstMon
Instrack -
InStat

пока всё заточено под локальную работу

изначально - это инструмент для телеграм-бота, но идея пошла чуть дальше

Базируется на instagrapi
https://github.com/adw0rd/instagrapi

для начала работы необходимо залогиниться 
(также в instagrapi есть возможность работы через прокси 
и с двухфакторной авторизацией, но здесь простой пример):

inst = InstaClient()
inst.login(login, password)

если не указать логин и пароль, то по-умолчанию ищет их в константах INST_LOGIN и INST_PASS
файлы сохраняет в папку ./inst (если её нет, то создаёт)
конфиги ищет в config.py (сейчас в bot_config.py, но это временно)

что умеет:
* снимать дамп id подписчиков по введённому имени пользователя и сохранять локально в txt
+ показ разницы между двумя дампами
- хранение данных в sqLite/MySQL
- работа с БД через ORM
- отдельный файл с моделями
- кеширование в файл
- кеширование через редис
- возможность скачать файл из бота
- периодические задачи через Celery для автоматизации отслеживания изменений в профиле
- возможно всё это в связке Flask+Celery+Redis+someDB+someORM (скорее всего PonyORM/SQLAlchemy+MySQL/sqLite)
- докер
- логи в файлах

"""

from instagrapi import Client, exceptions
from config import INST_LOGIN, INST_PASS
from datetime import datetime  # импортируется вместе с моделями
from models import *
import logging
import os


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('InstaClient')


class InstaClient(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)

    FIELDS = (
        'username',
        'full_name',
        'is_private',
        'is_verified',
        'biography',
        'is_business',
    )

    @staticmethod
    def create_and_login(login=INST_LOGIN, password=INST_PASS):
        """Возвращает залогиненый объект класса"""
        instance = InstaClient()
        if instance.login(login, password):
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
                user_id = self.user_id_from_username(user)
            except exceptions.ClientError:
                logger.error(f'Ошибка! Что-то с запросом. Возможно, не верно указан пользователь: {user}')
                raise
        return user_id

    @db_session
    def create_user_model(self, user_id: int or str, usershort: dict):
        """Фильтрует UserShort, создаёт экземпляр пользователя, сохраняет в БД и возвращает его"""
        user_id = int(user_id)
        user = User.get(id=user_id)

        if user:
            logger.debug(f'Пользователь найден в БД')
            # можно добавить обновление пользователя из usershort
            return user
        else:
            logger.debug(f'Пользователь в БД не найден, создаём его...')
            # фильтруем UserShort, т.к. нам нужны не все поля
            logger.debug(f'Фильтруем атрибуты пользователя {user_id}')
            usershort = {key: val for key, val in usershort.items() if key in self.FIELDS}

            # создаём пользователя в БД
            user = User(id=user_id, **usershort)
            logger.debug(f'Пользователь {user} создан')
            return user

    def users_to_db(self, users: dict):
        """Сохранение юзеров в БД и возврат сета юзеров"""
        user_set = set()

        for user_id, usershort in users.items():
            user = self.create_user_model(user_id, usershort.__dict__)
            user_set.add(user)  # возможно, лучше сохранить id, а не объекты?

        return user_set

    @db_session
    def make_relations_snap(self, snap_owner, user_set):
        """Создание снимка связей пользователя snap_owner"""
        # теперь надо создать снап и добавить в него всех пользователей
        # но сначала надо понять как не сложно передать подписчики это или подписки
        rel_snap = RelationshipsSnap(owner=snap_owner, )
        return rel_snap

    def save_followers(self, user=None):
        """Сохранение id подписчиков в файл"""
        user_id = self._get_correct_user_id(user)

        # получаем список подписчиков
        # придёт словарь с полной инфой о подписчиках вида
        # {'987654321': UserShort(pk='123456789', username='user_name', full_name='Имя', ... ), ... }
        logger.info(f'Получаем подписчиков пользователя {user}...')
        followers = self.user_followers(user_id)
        logger.info(f'Получено {len(followers)} подписчиков')

        if not followers:
            logger.info('Нечего сохранять, завершаем работу...')
            # тут надо логику пересмотреть
            if not self.username:
                logger.warning('Логин не выполнен, поэтому нельзя было получить подписчиков!')
            return

        # проверяем наличие папки под файлы, если нету - создаём
        if not os.path.isdir('inst'):
            logger.info('Не нашли папку inst, создаём...')
            os.mkdir('inst')

        # записываем в файл
        # сохраняем только ключи, так что у нас останутся только id пользователей
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        counter = 0
        with open(f'inst/{user}_followers_{now}.txt', 'w+') as f:
            for s in followers:
                f.write(s+'\n')
                counter += 1

        logger.info(f'Сохранено {counter} подписчиков')

        return True

    def followers_changes(self, user, show_id=False):
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

    def find_mutual_followers(self, user1, user2, cache=True):
        """Находит общих подписчиков между двумя пользователями"""

    def check_followers_changes(self, user=None):
        """Снимает дамп подписчиков, Возвращает изменения с последнего дампа"""
        user = self._get_correct_user_id(user)

        if self.save_followers(user):
            return self.followers_changes(user)

    def txt_to_db_snap(self, file='last'):
        """Экспортирует текстовый снимок в БД"""
        if file == 'last':
            pass
        else:
            pass


logger.info('Hi, InstaClient here')

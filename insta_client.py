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
- [в процессе] хранение данных в sqLite/MySQL
- [в процессе] работа с БД через ORM
- [в процессе] отдельный файл с моделями
- [в процессе] сохранение в тхт или в БД
- [в процессе] экспорт снапа из тхт в БД
- кеширование в файл
- кеширование через редис
- возможность скачать файл из бота
- периодические задачи через Celery для автоматизации отслеживания изменений в профиле
- возможно всё это в связке Flask+Celery+Redis+someDB+someORM (скорее всего PonyORM/SQLAlchemy+MySQL/sqLite)
- докер
- логи в файлах

REMINDER:
если обратиться к
https://www.instagram.com/{username}/?__a=1

то получаешь json с полной инфой по пользователю, но с огромным количеством мусора

маниакально старался не использовать re, но возможно, что зря
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
        'follower_count',
        'following_count',
        'public_email',
        'contact_phone_number',
        'external_url',
    )

    @staticmethod
    def create_and_login(login=INST_LOGIN, password=INST_PASS):
        """Возвращает залогиненый объект класса"""
        instance = InstaClient()
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
        users_set = set()

        for user_id, usershort in users.items():
            user = self.create_user_model(user_id, usershort.__dict__) if usershort \
                else self.create_user_model(user_id, {})  # костыль для случая, когда в usershort оказался None
            users_set.add(user)  # возможно, лучше сохранить id, а не объекты?

        return users_set

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
        return (
            RelationshipsSnap(owner=snap_owner, followers=users_set1) if relation_type == 'followers' else
            RelationshipsSnap(owner=snap_owner, followings=users_set1) if relation_type == 'followings' else
            RelationshipsSnap(owner=snap_owner, followers=users_set1, followings=users_set2) if relation_type == 'all' else
            None
        )

    def save_followers_txt(self, user=None):
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

        self.snap_to_txt(user, followers, relation_type='followers')

    def snap_to_txt(self, user, users, relation_type='followers'):
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
        with open(f'inst/{user}_{relation_type}_{now}.txt', 'w+') as f:
            for s in users:
                f.write(s+'\n')
                counter += 1

        logger.info(f'Сохранено {counter} пользователей')

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

    def find_mutual_followers(self, user1, user2, using_db=True):
        """Находит общих подписчиков между двумя пользователями"""

    def check_followers_changes(self, user=None):
        """Снимает дамп подписчиков, Возвращает изменения с последнего дампа"""
        user = self._get_correct_user_id(user)

        if self.save_followers_txt(user):
            return self.followers_changes(user)

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
                            if file[:len(user)] == user] and relation_type in file)  # берём только нужный юзернейм и сортируем
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

        logger.info('Запрашиваем краткую инфу о пользователях...')
        # запрашиваем UserShorts, собираем словарь вида:
        # {'987654321': UserShort(pk='123456789', username='user_name', full_name='Имя', ... ), ... }
        # можно вместо user_short_gql использовать user_info, но объём данных будет больше
        # и процесс будет медленнее
        for user_id in users:
            try:
                usershort = self.user_short_gql(user_id)
            except exceptions.ClientError:
                logger.error(f'Ошибка! Не удалось получить пользователя {user_id}')
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

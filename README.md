# InstaClient (а это - временный readme)

<p>Обёртка для instagrapi, сделана для расширения функционала, 
например, отслеживания того, кто подписался и отписался за какой-то период.</p>
<p>Основной минус сейчас в том, что Instagrapi - медленный клиент и тех же подписчиков получает медленно. 
Можно потерпеть полминуты, если их 500, но если больше - ждать очень долго. Поэтому либо я придумаю, 
как делать это быстро, либо это останется совсем уж бесполезной игрушкой.</p>

<p>Добавлена ветка instabot-engine, где я попробовал реализовать тот же функционал, но на устаревшем instabot, 
главный плюс которого в том, что он очень быстро получает список подписчиков. 
Однако всё остальное он делает довольно плохо (не может получить много юзернеймов - инста сбрасывает коннект).</p>

# Что уже умеет:

<ul>
<li>✔ снимать дамп id подписчиков по введённому имени пользователя и сохранять локально в txt</li>
<li>✔ показ разницы между двумя дампами</li>
<li>✔ хранение данных в sqLite/MySQL/PostgreSQL (но тестировал только sqLite и в конфиги пока не вынес настройки БД)</li>
<li>✔ работа с БД через ORM (Pony ORM)</li>
<li>✔ отдельный файл с моделями</li>
<li>✔ сохранение в БД</li>
<li>✔ показ разницы между двумя снапами подписчиков в БД</li>
<li>✔ обновление пользователя в БД (инфой из инсты)</li>
<li>~ <i>[в процессе]</i> костыль для добавления колонок в БД (т.к. Pony ORM не умеет в миграции). 
Пока может только добавлять колонку.</li>
<li>~ <i>[в процессе]</i> экспорт снапа из тхт в БД</li>
<li>~ кеширование в файл (формально оно уже есть, т.к. есть в instagrapi)</li>
<li>~ работа с прокси (формально есть в самом instagrapi, но у меня так и не завелось)</li>
<li>✘ возможность скачать файл из бота</li>
<li>✘ периодические задачи через Celery для автоматизации отслеживания изменений в профиле</li>
<li>✘ возможно всё это в связке Flask+Celery+Redis+sqLite (или любая другая база)+PonyORM</li>
<li>✘ докер</li>
<li>✘ логи в файлах</li>
</ul>

# Как пользоваться

<p>Кратенько</p>
<p>пока всё заточено под локальную работу, но уже умеет сохранять в БД (пока тестил только sqLite) </p>

<p>Базируется на instagrapi, поэтому доступны все те же методы + методы расширения
<a href="https://github.com/adw0rd/instagrapi" target="_blank">https://github.com/adw0rd/instagrapi</a></p>

<p>Для начала работы необходимо залогиниться 
(также в instagrapi есть возможность работы через прокси и с двухфакторной авторизацией, но здесь простой пример):</p>

`inst = InstaClient()`</br>
`inst.login(login, password)`

<p>Для ленивых (если в конфиге прописаны <code>INST_LOGIN</code> и <code>INST_PASS</code>):</p>

* <code>inst = InstaClient.create_and_login()</code>

<p>файлы дампа txt сохраняет в папку <code>./inst</code> (если её нет, то создаёт)</p>
<p>конфиги ищет в <code>config.py</code>, описание его чуть ниже</p>

<p>Снять снап подписчиков пользователя user и сохранить в БД: </p>

* `inst.save_followers(user)`

<p>Снять снап подписчиков пользователя user и сохранить в txt: </p>

* `inst.save_followers(user=user, mode='txt')`

<p>Сравнить два последних снапа подписчиков пользователя user из БД:</p>

* `inst.followers_changes_db(user)`

<p>Сравнить два последних снапа подписчиков пользователя user из txt:</p>

* `inst.followers_changes_txt(user)`

### Формат конфига примитивный:

<pre>
# Логин и пароль на вход
INST_LOGIN = ''
INST_PASS = ''
# двухфакторная авторизация

# TIME_ZONE =

# Support socks and http/https proxy “scheme://username:password@host:port”.
PROXY = ''
</pre>

<p>Чтобы менять настройки подключения к БД сейчас пока что нужно изменить строку в файле `models.py`, но потом будет вынесено тоже в конфиг:</p>

* `db.bind(provider='sqlite', filename='db.sqlite', create_db=True)`

<p>ЗЫ: маниакально старался не использовать re, но возможно, что зря</p>

<p>название ещё не придумал:</p>

* InstaClient - рабочее
* InstaGrappa ?
* InstaGrappi -
* InstagrYappi -
* Instalker -
* InstSpector
* InstMon
* Instrack -
* InStat


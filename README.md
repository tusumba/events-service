# events-service

Сервис **Events & Clubs** системы Tusumba: каталог и поиск мероприятий и клубов, страницы мероприятий и клубов, версии текстов, команда мероприятия и роли.

**Ответственный:** Михаил Коротков (задача #18891, OpenAPI делается вместе с Глебом Эстраихом).

## Что делает

- каталог мероприятий с сортировкой по дате, поиском по названию (`pg_trgm`) и фильтрами;
- каталог клубов и страница клуба;
- редактирование мероприятий и страниц клубов: каждое изменение создаёт новую версию текста (`event_versions`, `club_versions`), жалоба ссылается на конкретную версию;
- команда мероприятия и роли (владелец, администратор, редактор, контролёр), приглашения в команду;
- единственный источник правды о правах: остальные сервисы спрашивают роль пользователя у этого сервиса;
- создание мероприятия или клуба после одобрения заявки (событие `ApplicationApproved` от Moderation);
- загрузка фото на диск сервера через интерфейс `PhotoStorage`.

База данных `events_db`: `events`, `event_versions`, `clubs`, `club_versions`, `club_admins`, `event_team_members`, `team_invitations`.

## API

Внешний: `GET /v1/events`, `GET /v1/events/{id}`, `GET /v1/clubs`, `GET /v1/clubs/{id}`, `PATCH /v1/events/{id}`, `PATCH /v1/clubs/{id}`, `PUT /v1/events/{id}/photo`, `PUT /v1/clubs/{id}/photo`, `GET /v1/events/{id}/team`, `POST /v1/events/{id}/team/invitations`, `POST /v1/team-invitations/{id}/accept`, `PATCH` и `DELETE /v1/events/{id}/team/{userId}`, `GET /v1/events/{id}/versions`, `GET /v1/clubs/{id}/stats`.

Внутренний: `GET /internal/events/{id}/permissions`, `GET /internal/events/{id}/versions/{versionId}`, `GET /internal/clubs/{id}/versions/{versionId}`.

События в брокер: `EventPublished`, `EventUpdated`. Потребляет `ApplicationApproved`.

Закрывает требования: #18091, #18093, #18098, #18103, #18105, #18110, #18111, #18112, #18113, каталог и поиск клубов (#18626, #18627).

## Стек

Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16 (расширение `pg_trgm`), RabbitMQ (FastStream).

## Запуск

Описание появится после готовности шаблона сервиса (#18887) и стенда (#18905). Окружение целиком поднимается из репозитория `deploy`.

## Документация

Wiki проекта: https://ai.nsu.ru/projects/tusumba/wiki/Архитектура. Контракт API: OpenAPI v1 (#18891). Задачи ведутся в Redmine: https://ai.nsu.ru/projects/tusumba. Issues и Wiki GitHub выключены.

## Правила работы

Ветки, коммиты, pull request и code review описаны в [CONTRIBUTING.md](https://github.com/tusumba/.github/blob/main/CONTRIBUTING.md). Коротко:

- ветка называется `feature/<номер задачи Redmine>-<пара слов>`, например `feature/18901-login`;
- номер задачи указывается в каждом коммите и в названии PR;
- в `main` изменения попадают только через PR с одним одобрением и зелёным CI, прямой push и force push запрещены.

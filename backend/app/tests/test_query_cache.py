"""Юнит-тесты кэша статических справочников (_query_cache, #392/#393).

Проверяем ровно те инварианты, на которых держится N+1-рефактор /calculate:
повторный lookup в пределах сессии не эмитит новый SQL, разные ключи не
коллизируют, негативный результат тоже кэшируется, а между сессиями кэш на
session.info не протекает. Идентичность объектов тут ничего не доказала бы
(identity map SQLAlchemy и без кэша вернул бы тот же объект по PK), поэтому
регрессию ловим по числу реально выполненных запросов.
"""
from contextlib import contextmanager

from sqlalchemy import event

from app.db.session import engine
from app.services import _query_cache as qc
from app.tests.conftest import TestingSessionLocal


@contextmanager
def count_queries():
    """Считает SQL-стейтменты, реально ушедшие в БД за время блока."""
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def test_repeated_lookup_hits_cache_not_db(db_session):
    with count_queries() as c:
        first = qc.material_by_name(db_session, "Краска для стен")
        n_after_first = c["n"]
        second = qc.material_by_name(db_session, "Краска для стен")
        n_after_second = c["n"]
    assert first is second is not None
    assert n_after_first >= 1                 # первый вызов сходил в БД
    assert n_after_second == n_after_first    # второй — из кэша, без нового SQL


def test_distinct_names_do_not_collide(db_session):
    paint = qc.material_by_name(db_session, "Краска для стен")
    laminate = qc.material_by_name(db_session, "Ламинат")
    assert paint is not None and laminate is not None
    assert paint.slug == "paint_walls"
    assert laminate.slug == "laminate"


def test_negative_result_is_cached(db_session):
    with count_queries() as c:
        first = qc.material_by_name(db_session, "Нет такого материала")
        n_after_first = c["n"]
        second = qc.material_by_name(db_session, "Нет такого материала")
        n_after_second = c["n"]
    assert first is None and second is None
    assert n_after_first >= 1
    assert n_after_second == n_after_first    # None тоже закэширован


def test_cache_does_not_leak_between_sessions(db_session):
    qc.source_by_name(db_session, "seed")
    assert "_cache_source_by_name" in db_session.info
    other = TestingSessionLocal()
    try:
        # Своя сессия-запрос → свой чистый session.info, кэш не разделяется.
        assert "_cache_source_by_name" not in other.info
    finally:
        other.close()


def test_finish_key_variants_resolved(db_session):
    variants = qc.material_variants_by_finish_key(db_session, "floor.laminate")
    tiers = {m.variant_tier for m in variants}
    assert tiers == {"min", "avg", "max"}

import threading
from sqlalchemy import create_engine
from sqlalchemy import Column, BigInteger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.pool import QueuePool
from bot.config import DB

BASE = declarative_base()


class BanList(BASE):
    __tablename__ = "banlist"
    user_id = Column(BigInteger, primary_key=True)

    def __init__(self, user_id):
        self.user_id = user_id


def start() -> scoped_session:
    engine = create_engine(
        DB.DB_URL,
        client_encoding="utf8",
        poolclass=QueuePool,           # Better than StaticPool
        pool_pre_ping=True,            # 🔥 This helps detect dead connections
        pool_recycle=300,              # Recycle every 5 minutes
        pool_size=10,
        max_overflow=20,
    )
    BASE.metadata.bind = engine
    BASE.metadata.create_all(engine)
    return scoped_session(sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))


SESSION = start()
INSERTION_LOCK = threading.RLock()


async def ban_user(user_id: int):
    with INSERTION_LOCK:
        session = SESSION()
        try:
            usr = session.query(BanList).filter_by(user_id=user_id).one()
            return False  # already banned
        except NoResultFound:
            usr = BanList(user_id=user_id)
            session.add(usr)
            session.commit()
            return True
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()   # Important!


async def is_banned(user_id: int):
    with INSERTION_LOCK:
        session = SESSION()
        try:
            session.query(BanList).filter_by(user_id=user_id).one()
            return True
        except NoResultFound:
            return False
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()


async def unban_user(user_id: int):
    with INSERTION_LOCK:
        session = SESSION()
        try:
            usr = session.query(BanList).filter_by(user_id=user_id).one()
            session.delete(usr)
            session.commit()
            return True
        except NoResultFound:
            return False
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

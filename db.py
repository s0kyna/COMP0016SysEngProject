# db.py

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base


# Always store the database in the project root,
# regardless of the directory Python is run from.
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "erp_database.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


def initialize_database():
    Base.metadata.create_all(engine)
    print("Database initialized successfully.")


def get_session():
    return SessionLocal()
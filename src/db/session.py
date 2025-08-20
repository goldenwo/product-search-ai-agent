from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.utils.config import DATABASE_URL

engine = create_async_engine(str(DATABASE_URL), pool_pre_ping=True)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

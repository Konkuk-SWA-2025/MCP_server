import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from dotenv import load_dotenv

# .env 파일에서 DB URL 로드
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./inventory.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 다이어그램: 'DB 테이블' (사용자 정보) ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, comment="고유키")
    user_id = Column(String(255), unique=True, index=True, comment="각 플랫폼별 사용자 아이디")
    sheet_id = Column(String(255), comment="사용할 구글 시트 번호")
    channel = Column(String(50), comment="사용한 채팅 플랫폼")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    modified_at = Column(DateTime(timezone=True), onupdate=func.now())

# --- 다이어그램: 'prompt 정보' (로그) ---
class PromptLog(Base):
    __tablename__ = "prompt_logs"
    id = Column(Integer, primary_key=True, index=True, comment="고유키")
    user_id = Column(String(255), index=True, comment="각 플랫폼별 사용자 아이디")
    sheet_id = Column(String(255), comment="사용할 구글 시트 번호")
    message = Column(String(2000), comment="사용자가 채팅에 입력한 메세지")
    channel = Column(String(50), comment="사용한 채팅 플랫폼")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    modified_at = Column(DateTime(timezone=True), onupdate=func.now())

# --- 다이어그램: '툴 정의' (입출고 기록용 로그) ---
class StockLog(Base):
    __tablename__ = "stock_logs"
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String(255), index=True, comment="품목 이름")
    quantity_change = Column(Float, comment="변동 수량")
    sheet_id = Column(String(255), comment="사용할 구글 시트 번호")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# --- DB 생성 및 세션 ---
def create_tables():
    """서버 시작 시 테이블 생성"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """FastAPI 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
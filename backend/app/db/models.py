from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db.database import Base


class ModelRecord(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), unique=True, nullable=False)
    provider = Column(String(100))
    version = Column(String(50))
    last_seen = Column(DateTime, default=datetime.utcnow)


class Attack(Base):
    __tablename__ = "attacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)  # PROMPT_INJECTION/JAILBREAK/CONTEXT_MANIPULATION/DATA_LEAKAGE
    prompt = Column(Text, nullable=False)
    description = Column(Text)
    severity = Column(String(20), nullable=False)  # low/medium/high/critical

    test_runs = relationship("TestRun", back_populates="attack")


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(200), nullable=False)
    attack_id = Column(Integer, ForeignKey("attacks.id"))
    prompt_sent = Column(Text)
    model_response = Column(Text)
    score = Column(Float)
    verdict = Column(String(20))  # PASS/FAIL/UNCERTAIN
    reason = Column(String(500))
    latency_ms = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

    attack = relationship("Attack", back_populates="test_runs")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(200), nullable=False)
    report_data = Column(JSON, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    desc,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from nse_bot.config import get_settings


class Base(DeclarativeBase):
    pass


class TradeRecord(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_key: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    risk_reward: Mapped[float] = mapped_column(Float, nullable=False)
    probability_pct: Mapped[float] = mapped_column(Float, nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    order_ref: Mapped[str] = mapped_column(String(128), default="")
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PipelineRunRecord(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    universe_size: Mapped[int] = mapped_column(Integer, default=0)
    ideas_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(String(512), default="")


class BotStateRecord(Base):
    __tablename__ = "bot_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String(4000), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Storage:
    def __init__(self) -> None:
        settings = get_settings()
        self.engine = create_engine(f"sqlite:///{settings.db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)

    def save_pipeline_run(self, universe_size: int, ideas_count: int, notes: str = "") -> None:
        with self.SessionLocal() as session:
            now = datetime.now(timezone.utc)
            session.add(
                PipelineRunRecord(
                    started_at=now,
                    completed_at=now,
                    universe_size=universe_size,
                    ideas_count=ideas_count,
                    notes=notes,
                )
            )
            session.commit()

    def save_trade(
        self,
        trade_id: str,
        symbol: str,
        instrument_key: str,
        side: str,
        quantity: int,
        entry: float,
        stop_loss: float,
        target: float,
        risk_reward: float,
        probability_pct: float,
        mode: str,
        status: str,
        order_ref: str = "",
        pnl: float = 0.0,
    ) -> None:
        with self.SessionLocal() as session:
            now = datetime.now(timezone.utc)
            row = TradeRecord(
                trade_id=trade_id,
                symbol=symbol,
                instrument_key=instrument_key,
                side=side,
                quantity=quantity,
                entry=entry,
                stop_loss=stop_loss,
                target=target,
                risk_reward=risk_reward,
                probability_pct=probability_pct,
                mode=mode,
                status=status,
                order_ref=order_ref,
                pnl=pnl,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()

    def update_trade_status(self, trade_id: str, status: str, pnl: float | None = None) -> None:
        with self.SessionLocal() as session:
            row = session.execute(select(TradeRecord).where(TradeRecord.trade_id == trade_id)).scalar_one_or_none()
            if not row:
                return
            row.status = status
            if pnl is not None:
                row.pnl = pnl
            row.updated_at = datetime.now(timezone.utc)
            session.commit()

    def update_trade_pnl(self, trade_id: str, pnl: float) -> None:
        with self.SessionLocal() as session:
            row = session.execute(select(TradeRecord).where(TradeRecord.trade_id == trade_id)).scalar_one_or_none()
            if not row:
                return
            row.pnl = pnl
            row.updated_at = datetime.now(timezone.utc)
            session.commit()

    def get_open_trades(self) -> list[TradeRecord]:
        with self.SessionLocal() as session:
            rows = session.execute(
                select(TradeRecord).where(TradeRecord.status == "OPEN").order_by(desc(TradeRecord.created_at))
            ).scalars()
            return list(rows)

    def get_all_trades(self, limit: int = 300) -> list[TradeRecord]:
        with self.SessionLocal() as session:
            rows = session.execute(select(TradeRecord).order_by(desc(TradeRecord.created_at)).limit(limit)).scalars()
            return list(rows)

    def set_state(self, key: str, value: str) -> None:
        with self.SessionLocal() as session:
            row = session.execute(select(BotStateRecord).where(BotStateRecord.key == key)).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row:
                row.value = value
                row.updated_at = now
            else:
                session.add(BotStateRecord(key=key, value=value, updated_at=now))
            session.commit()

    def get_state(self, key: str) -> str | None:
        with self.SessionLocal() as session:
            row = session.execute(select(BotStateRecord).where(BotStateRecord.key == key)).scalar_one_or_none()
            if not row:
                return None
            return row.value

    @staticmethod
    def rows_to_dict(rows: Iterable[TradeRecord]) -> list[dict]:
        out = []
        for r in rows:
            out.append(
                {
                    "trade_id": r.trade_id,
                    "symbol": r.symbol,
                    "instrument_key": r.instrument_key,
                    "side": r.side,
                    "quantity": r.quantity,
                    "entry": r.entry,
                    "stop_loss": r.stop_loss,
                    "target": r.target,
                    "risk_reward": r.risk_reward,
                    "probability_pct": r.probability_pct,
                    "mode": r.mode,
                    "status": r.status,
                    "order_ref": r.order_ref,
                    "pnl": r.pnl,
                    "created_at": r.created_at.isoformat(),
                    "updated_at": r.updated_at.isoformat(),
                }
            )
        return out

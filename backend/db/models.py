# backend/db/models.py
"""
Схема БД для онлайн-школы (родитель, дети, уроки, платежи, история диалога).
Гарантированно компилируется на SQLAlchemy 2.x.
"""
from __future__ import annotations
from datetime import date
import enum
from sqlalchemy.sql import false
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,  
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import Date, Integer, String, Table, Column, ForeignKey, BigInteger
from sqlalchemy.orm import (
    Mapped,
    declarative_base,
    mapped_column,
    relationship,
)
from sqlalchemy.sql.expression import false

Base = declarative_base()

# --------------------------------------------------------------------------- #
# 1. Справочники (Enum)
# --------------------------------------------------------------------------- #

class ParentStatus(enum.Enum):
    SINGLE = "одинокий"
    MARRIED = "в_браке"
    LARGE_FAMILY = "многодетный"
    DIVORCED = "в_разводе"

class OnboardingStep(enum.Enum):
    NOT_STARTED = "не_начат"
    PARENT_DATA = "данные_родителя"
    CHILDREN_COUNT = "количество_детей"
    CHILDREN_DATA = "данные_детей"
    CONFIRMATION = "подтверждение"
    COMPLETED = "завершён"

class TrialLessonStatus(enum.Enum):
    PLANNED = "запланирован"
    COMPLETED = "проведён"
    CANCELLED = "отменён"
    NO_SHOW = "не_явился"

class PaymentStatus(enum.Enum):
    PENDING = "ожидание_оплаты"
    IN_PROCESS = "обработка"
    PAID = "оплачен"
    PARTIALLY_REFUNDED = "частичный_возврат"
    REFUNDED = "полный_возврат"
    FAILED = "ошибка"
    CANCELLED = "отменён"

# --------------------------------------------------------------------------- #
# 2. Основные сущности
# --------------------------------------------------------------------------- #

class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    parent_status: Mapped[Optional[ParentStatus]] = mapped_column(Enum(ParentStatus, name="parent_status"), nullable=True)

    onboarding_step: Mapped[OnboardingStep] = mapped_column(
        Enum(OnboardingStep, name="onboarding_step_enum"), # Даем уникальное имя Enum для БД
        default=OnboardingStep.NOT_STARTED,
        nullable=False,
    )
    onboarding_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    onboarding_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_enrolled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    irrelevant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    children: Mapped[List["Child"]] = relationship("Child", back_populates="parent", cascade="all, delete-orphan")
    trial_lessons: Mapped[List["TrialLesson"]] = relationship("TrialLesson", back_populates="parent", cascade="all, delete-orphan")
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="parent", cascade="all, delete-orphan")
    dialog_history: Mapped[List["DialogHistory"]] = relationship("DialogHistory", back_populates="parent", cascade="all, delete-orphan")
    feedbacks: Mapped[List["Feedback"]] = relationship("Feedback", back_populates="parent", cascade="all, delete-orphan")
    waitlist_entries: Mapped[List["WaitlistEntry"]] = relationship("WaitlistEntry", back_populates="parent", cascade="all, delete-orphan")
    b24_deal_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

class Child(Base):
    __tablename__ = "children"
    id: Mapped[int] =  mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    interests: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    course_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lessons_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    parent: Mapped["Parent"] = relationship(back_populates="children")
    trial_lessons: Mapped[List["TrialLesson"]] = relationship("TrialLesson", back_populates="child", cascade="all, delete-orphan")
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="child", cascade="all, delete-orphan")
    b24_deal_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    
class TrialLesson(Base):
    __tablename__ = "trial_lessons"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), nullable=False)

    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    event_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    teacher_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    bitrix_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[TrialLessonStatus] = mapped_column(
        Enum(TrialLessonStatus, name="trial_lesson_status"),
        default=TrialLessonStatus.PLANNED,
        nullable=False,
        index=True
    )
    course_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    parent: Mapped["Parent"] = relationship(back_populates="trial_lessons")
    child: Mapped["Child"] = relationship(back_populates="trial_lessons")
    feedbacks: Mapped[List["Feedback"]] = relationship("Feedback", back_populates="lesson", cascade="all, delete-orphan")
    # Флаг, который показывает, было ли отправлено напоминание за 24 часа
    reminder_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), index=True)
    # Флаг для напоминания за 1 час
    reminder_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), index=True)
    # поле для напоминания за 10 минут
    reminder_10min_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), index=True)
    # Флаги уведомлений о событиях
    notified_new: Mapped[bool] = mapped_column(Boolean,server_default=false(), index=True)
    notified_reschedule: Mapped[bool] = mapped_column(Boolean, server_default=false(), index=True)
    notified_cancel: Mapped[bool] = mapped_column(Boolean,server_default=false(), index=True)

class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING, nullable=False)
    external_payment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    parent: Mapped["Parent"] = relationship(back_populates="payments")
    child: Mapped["Child"] = relationship(back_populates="payments")

class DialogHistory(Base):
    __tablename__ = "dialog_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(
        BigInteger,  # ← тоже BigInteger
        ForeignKey("parents.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fsm_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    parent: Mapped["Parent"] = relationship(back_populates="dialog_history")

class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("trial_lessons.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    parent: Mapped["Parent"] = relationship(back_populates="feedbacks")
    lesson: Mapped["TrialLesson"] = relationship(back_populates="feedbacks")

class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parents.id", ondelete="CASCADE"), nullable=False)
    contact: Mapped[str] = mapped_column(String(200), nullable=False)
    age_group: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    deal_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    parent: Mapped["Parent"] = relationship(back_populates="waitlist_entries")


# ---------------------------------------------------------------------------
# Ассоциативные таблицы для Teacher и Group
# ---------------------------------------------------------------------------
teacher_child_association = Table(
    "teacher_child_association",      # Имя таблицы в базе данных
    Base.metadata,                    # Метаданные базы (общие для всех таблиц)
    Column("teacher_id", ForeignKey("teachers.id"), primary_key=True),  # Внешний ключ на таблицу teachers
    Column("child_id", ForeignKey("children.id"), primary_key=True),   # Внешний ключ на таблицу children
    extend_existing=True)

group_child_association = Table(
    "group_child_association",
    Base.metadata,
    Column("group_id", ForeignKey("groups.id"), primary_key=True),
    Column("child_id", ForeignKey("children.id"), primary_key=True),
)

# ---------------------------------------------------------------------------
# ORM-модель для учителя (Teacher)
# ---------------------------------------------------------------------------
class Teacher(Base):
    __tablename__ = "teachers"  # Имя таблицы в базе

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # Первичный ключ (ID)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)          # Имя учителя (обязательное)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)           # Фамилия учителя (обязательное)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)       # Дата рождения (опционально)
    telegram: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)    # Телеграм username (опционально)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)       # Телефон (опционально)
    telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)
    lesson_link = Column(String, nullable=True)
    # Связь many-to-many с детьми через ассоциативную таблицу
    children: Mapped[List[Child]] = relationship(
        "Child",                 
        secondary=teacher_child_association,
        lazy="selectin",
        back_populates=None
    )

    # Связь один-ко-многим с группами, которые ведёт этот педагог
    groups: Mapped[List["Group"]] = relationship(
        "Group",
        back_populates="teacher",
        lazy="selectin"
    )

# ---------------------------------------------------------------------------
# ORM-модель для группы (Group)
# ---------------------------------------------------------------------------
class Group(Base):
    __tablename__ = "groups"  # Имя таблицы в базе

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # PK группы
    name: Mapped[str] = mapped_column(String(100), nullable=False)                # Имя группы (обязательное)

    # Внешний ключ к таблице teachers — у группы один педагог
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)

    # Связь many-to-many с детьми через промежуточную таблицу
    children: Mapped[List[Child]] = relationship(
        "Child",                      # Целевая модель
        secondary=group_child_association,  # Таблица связей many-to-many "группа ⇄ дети"
        lazy="selectin"               # Оптимизированная загрузка
    )

    # Обратная связь к учителю — одна группа принадлежит одному учителю
    teacher: Mapped[Teacher] = relationship(
        "Teacher",
        back_populates="groups"
    )


import datetime
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Date, DateTime,
    Time, ForeignKey, UniqueConstraint, text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
Session = sessionmaker(bind=engine)
Base = declarative_base()


# ── Models ───────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    first_name = Column(String, default="")
    username = Column(String, default="")

    tasks_owned = relationship(
        "Task", back_populates="owner_rel", foreign_keys="Task.owner_id"
    )
    tasks_created = relationship(
        "Task", back_populates="creator_rel", foreign_keys="Task.creator_id"
    )

    @property
    def display_name(self):
        if self.username:
            return f"@{self.username}"
        return self.first_name or f"User {self.telegram_id}"


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, nullable=False)
    title = Column(String, default="")
    timezone = Column(String, default="Asia/Dushanbe")
    next_task_number = Column(Integer, default=1)

    members = relationship("GroupMember", back_populates="group")
    tasks = relationship("Task", back_populates="group")


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)

    group = relationship("Group", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_user"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    display_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String, default="open")       # open / done / dropped
    rolled_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    due_time = Column(Time, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    group = relationship("Group", back_populates="tasks")
    owner_rel = relationship("User", back_populates="tasks_owned", foreign_keys=[owner_id])
    creator_rel = relationship("User", back_populates="tasks_created", foreign_keys=[creator_id])


class Streak(Base):
    __tablename__ = "streaks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    current_streak = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)
    last_completed_date = Column(Date, nullable=True)

    user = relationship("User")
    group = relationship("Group")

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_streak_user_group"),
    )


# ── Database helpers ─────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(engine)
    # Migrate: add due_time column if missing (for existing databases)
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT due_time FROM tasks LIMIT 1"))
        except Exception:
            try:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN due_time TIME"))
                conn.commit()
            except Exception:
                pass


def get_or_create_user(session, telegram_id, first_name="", username=""):
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
        )
        session.add(user)
        session.flush()
    else:
        if first_name:
            user.first_name = first_name
        if username:
            user.username = username
    return user


def get_or_create_group(session, chat_id, title=""):
    group = session.query(Group).filter_by(chat_id=chat_id).first()
    if not group:
        group = Group(chat_id=chat_id, title=title)
        session.add(group)
        session.flush()
    else:
        if title:
            group.title = title
    return group


def ensure_membership(session, group, user):
    exists = (
        session.query(GroupMember)
        .filter_by(group_id=group.id, user_id=user.id)
        .first()
    )
    if not exists:
        session.add(GroupMember(group_id=group.id, user_id=user.id))


def create_task(session, group, owner, creator, title, due_date, due_time=None):
    num = group.next_task_number
    group.next_task_number += 1
    task = Task(
        group_id=group.id,
        display_number=num,
        title=title,
        owner_id=owner.id,
        creator_id=creator.id,
        due_date=due_date,
        due_time=due_time,
    )
    session.add(task)
    session.flush()
    return task


def get_open_tasks_for_date(session, group_id, target_date):
    return (
        session.query(Task)
        .filter(
            Task.group_id == group_id,
            Task.status == "open",
            Task.due_date <= target_date,
        )
        .order_by(Task.owner_id, Task.due_date, Task.display_number)
        .all()
    )


def get_task_by_number(session, group_id, display_number):
    return (
        session.query(Task)
        .filter(
            Task.group_id == group_id,
            Task.display_number == display_number,
            Task.status == "open",
        )
        .first()
    )


def get_all_tasks_by_number(session, group_id, display_number):
    """Find a task by number regardless of status (for lookup)."""
    return (
        session.query(Task)
        .filter(
            Task.group_id == group_id,
            Task.display_number == display_number,
        )
        .first()
    )


def get_all_open_tasks_for_group(session, group_id):
    """Get all open tasks for a group, regardless of date."""
    return (
        session.query(Task)
        .filter(
            Task.group_id == group_id,
            Task.status == "open",
        )
        .order_by(Task.due_date, Task.owner_id, Task.display_number)
        .all()
    )


def search_open_tasks_by_name(session, group_id, search_term):
    """Find open tasks whose title contains the search term (case-insensitive)."""
    return (
        session.query(Task)
        .filter(
            Task.group_id == group_id,
            Task.status == "open",
            Task.title.ilike(f"%{search_term}%"),
        )
        .order_by(Task.display_number)
        .all()
    )


def get_or_create_streak(session, user_id, group_id):
    streak = (
        session.query(Streak)
        .filter_by(user_id=user_id, group_id=group_id)
        .first()
    )
    if not streak:
        streak = Streak(user_id=user_id, group_id=group_id)
        session.add(streak)
        session.flush()
    return streak

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    plain_password = Column(String(100), nullable=True)  # Helper for admin/tutors to share login info with kids
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), default="student", nullable=False)  # 'admin', 'tutor', 'student'
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Contact information (individual for each tutor)
    telegram = Column(String(150), nullable=True)
    telegram_handle = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(100), nullable=True)
    whatsapp = Column(String(150), nullable=True)
    max_link = Column(String(200), nullable=True)

    # Relationships
    group = relationship("Group", back_populates="students", foreign_keys=[group_id])
    submissions = relationship("Submission", back_populates="student", cascade="all, delete-orphan")
    quiz_results = relationship("QuizResult", back_populates="student", cascade="all, delete-orphan")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    tutor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tutor = relationship("User", foreign_keys=[tutor_id], backref="assigned_groups")
    students = relationship("User", back_populates="group", foreign_keys="User.group_id")
    modules = relationship("Module", back_populates="group", cascade="all, delete-orphan", order_by="Module.order")


class Module(Base):
    __tablename__ = "modules"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    order = Column(Integer, default=1)

    # Relationships
    group = relationship("Group", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan", order_by="Lesson.order")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    deadline = Column(DateTime, nullable=True)
    order = Column(Integer, default=1)
    has_homework = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    module = relationship("Module", back_populates="lessons")
    materials = relationship("AssignmentMaterial", back_populates="lesson", cascade="all, delete-orphan")
    quiz = relationship("Quiz", back_populates="lesson", uselist=False, cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="lesson", cascade="all, delete-orphan")


class AssignmentMaterial(Base):
    __tablename__ = "assignment_materials"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    material_type = Column(String(20), nullable=False)  # 'file', 'link', 'text'
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    file_url = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    gdrive_file_id = Column(String(100), nullable=True)
    external_link = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    lesson = relationship("Lesson", back_populates="materials")


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), unique=True, nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    passing_score = Column(Integer, default=70)  # Percentage required (e.g. 70%)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    lesson = relationship("Lesson", back_populates="quiz")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.order")
    results = relationship("QuizResult", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), default="single")  # 'single', 'multiple', 'text'
    options_json = Column(Text, default="[]")  # JSON array of options e.g. ["Python", "C++", "Java"]
    correct_answers_json = Column(Text, default="[]")  # JSON array of correct indices or answer text
    points = Column(Integer, default=1)
    order = Column(Integer, default=1)

    # Relationships
    quiz = relationship("Quiz", back_populates="questions")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(30), default="submitted")  # 'submitted', 'reviewed', 'needs_revision'
    text_answer = Column(Text, nullable=True)
    file_url = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    gdrive_file_id = Column(String(100), nullable=True)
    grade = Column(String(50), nullable=True)  # e.g. "5+", "10/10", "Зачтено"
    tutor_comment = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    # Relationships
    lesson = relationship("Lesson", back_populates="submissions")
    student = relationship("User", back_populates="submissions")


class QuizResult(Base):
    __tablename__ = "quiz_results"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, default=0)
    max_score = Column(Integer, default=0)
    percentage = Column(Integer, default=0)
    passed = Column(Boolean, default=False)
    answers_json = Column(Text, default="{}")
    submitted_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    quiz = relationship("Quiz", back_populates="results")
    student = relationship("User", back_populates="quiz_results")

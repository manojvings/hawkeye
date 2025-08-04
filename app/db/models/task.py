# app/db/models/task.py
"""Task management model"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index, Enum, DateTime
from sqlalchemy.orm import relationship

from app.db.models.base import Base, TimestampMixin, UUIDMixin
from app.db.models.enums import TaskStatus


class Task(Base, UUIDMixin, TimestampMixin):
    """Task model for case workflow"""
    __tablename__ = "tasks"

    # Task fields
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING, index=True)
    order_index = Column(Integer, nullable=False, default=0)
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Foreign keys
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    # Relationships
    case = relationship("Case", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_id], backref="assigned_tasks")
    created_by = relationship("User", foreign_keys=[created_by_id], backref="created_tasks")

    __table_args__ = (
        Index('idx_task_case_order', 'case_id', 'order_index'),
        Index('idx_task_assignee_status', 'assignee_id', 'status'),
        Index('idx_task_uuid', 'uuid'),
    )

    def __repr__(self):
        return f"<Task title={self.title} status={self.status}>"
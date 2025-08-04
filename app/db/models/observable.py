# app/db/models/observable.py
"""Observable (IOC/Artifact) model"""
from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, ForeignKey, Index, Enum
from sqlalchemy.orm import relationship

from app.db.models.base import Base, TimestampMixin, UUIDMixin
from app.db.models.enums import ObservableType, TLP


class Observable(Base, UUIDMixin, TimestampMixin):
    """Observable model for IOCs and artifacts"""
    __tablename__ = "observables"

    # Observable fields
    data_type = Column(Enum(ObservableType), nullable=False, index=True)
    data = Column(String(1000), nullable=False, index=True)  # The actual observable value
    tlp = Column(Enum(TLP), nullable=False, default=TLP.AMBER)
    is_ioc = Column(Boolean, default=False, nullable=False, index=True)
    tags = Column(JSON, default=list, nullable=False)
    source = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    sighted_count = Column(Integer, default=0, nullable=False)

    # Foreign keys
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    # Relationships
    case = relationship("Case", back_populates="observables")
    created_by = relationship("User", backref="created_observables")

    __table_args__ = (
        Index('idx_observable_type_ioc', 'data_type', 'is_ioc'),
        Index('idx_observable_data', 'data'),
        Index('idx_observable_case', 'case_id'),
        Index('idx_observable_uuid', 'uuid'),
    )

    def __repr__(self):
        return f"<Observable type={self.data_type} data={self.data[:50]}>"
"""Database models for ETN monitoring."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class TransportNode(Base):
    """Edge Transport Node from NSX-T."""
    __tablename__ = 'transport_nodes'
    
    id = Column(String, primary_key=True)  # node_id from NSX
    display_name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    maintenance_mode = Column(String)  # ENABLED, DISABLED
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    certificate_checks = relationship("CertificateCheck", back_populates="node", cascade="all, delete-orphan")
    events = relationship("NodeEvent", back_populates="node", cascade="all, delete-orphan")
    notifications = relationship("TelegramNotification", back_populates="node", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<TransportNode(id={self.id}, name={self.display_name}, ip={self.ip_address})>"


class CertificateCheck(Base):
    """Certificate check history."""
    __tablename__ = 'certificate_checks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String, ForeignKey('transport_nodes.id'), nullable=False)
    cert_expiry_date = Column(DateTime, nullable=True)  # ✅ FIXED: Can be NULL if check failed
    days_remaining = Column(Integer, nullable=False)
    check_status = Column(String, nullable=False)  # success, error, timeout, ssh_failed
    error_message = Column(Text)
    checked_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    node = relationship("TransportNode", back_populates="certificate_checks")
    
    def __repr__(self):
        return f"<CertificateCheck(node_id={self.node_id}, days_remaining={self.days_remaining}, status={self.check_status})>"


class NodeEvent(Base):
    """Transport node lifecycle events."""
    __tablename__ = 'node_events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String, ForeignKey('transport_nodes.id'), nullable=False)
    event_type = Column(String, nullable=False)  # added, removed, reappeared
    display_name = Column(String)
    ip_address = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    node = relationship("TransportNode", back_populates="events")
    
    def __repr__(self):
        return f"<NodeEvent(node_id={self.node_id}, type={self.event_type}, at={self.created_at})>"


class TelegramNotification(Base):
    """Telegram notification tracking to avoid spam."""
    __tablename__ = 'telegram_notifications'
    __table_args__ = (
        UniqueConstraint('node_id', 'notification_type', 'notification_date', name='_node_notification_date_uc'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String, ForeignKey('transport_nodes.id'), nullable=False)
    notification_type = Column(String, nullable=False)  # cert_expiring_30d, cert_expiring_7d, cert_expired
    notification_date = Column(String, nullable=False)  # YYYY-MM-DD to track daily uniqueness
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    node = relationship("TransportNode", back_populates="notifications")
    
    def __repr__(self):
        return f"<TelegramNotification(node_id={self.node_id}, type={self.notification_type})>"
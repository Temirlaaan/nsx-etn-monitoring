"""Pydantic schemas for API responses."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class TransportNodeSchema(BaseModel):
    """Transport Node response schema."""
    id: str
    display_name: str
    ip_address: str
    maintenance_mode: Optional[str] = None
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)


class CertificateCheckSchema(BaseModel):
    """Certificate check response schema."""
    id: int
    node_id: str
    cert_expiry_date: Optional[datetime] = None
    days_remaining: Optional[int] = None
    check_status: str
    error_message: Optional[str] = None
    checked_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class NodeEventSchema(BaseModel):
    """Node event response schema."""
    id: int
    node_id: str
    event_type: str
    display_name: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class NodeDetailSchema(BaseModel):
    """Detailed node info with latest certificate check."""
    node: TransportNodeSchema
    latest_cert_check: Optional[CertificateCheckSchema] = None
    
    model_config = ConfigDict(from_attributes=True)


class DashboardStatsSchema(BaseModel):
    """Dashboard statistics."""
    total_nodes: int
    active_nodes: int
    inactive_nodes: int
    certs_expiring_soon: int  # < 30 days
    certs_expiring_very_soon: int  # < 7 days
    certs_expired: int  # <= 0 days
    last_nsx_sync: Optional[datetime] = None
    last_cert_check: Optional[datetime] = None

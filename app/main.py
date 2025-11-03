"""FastAPI application for ETN certificate monitoring."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.database import get_db, init_db
from app.models import TransportNode, CertificateCheck, NodeEvent
from app.schemas import (
    TransportNodeSchema, NodeDetailSchema, NodeEventSchema,
    DashboardStatsSchema, CertificateCheckSchema
)
from app.scheduler import SchedulerService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler_service: Optional[SchedulerService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    global scheduler_service
    
    # Startup
    logger.info("Starting ETN Certificate Monitor...")
    
    # Validate configuration
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    # Start scheduler
    scheduler_service = SchedulerService()
    scheduler_service.start()
    
    # Run initial sync
    await scheduler_service.run_initial_sync()
    
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    if scheduler_service:
        scheduler_service.shutdown()
    logger.info("Application stopped")


# Create FastAPI app
app = FastAPI(
    title="ETN Certificate Monitor",
    description="Monitor Edge Transport Node SSL certificates from NSX-T Manager",
    version="1.0.0",
    lifespan=lifespan
)

# Setup templates
templates = Jinja2Templates(directory="templates")


# === Web UI Endpoints ===

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Main dashboard page."""
    
    # Get all active nodes
    result = await db.execute(
        select(TransportNode)
        .where(TransportNode.is_active == True)
        .order_by(TransportNode.display_name)
    )
    nodes = result.scalars().all()
    
    # Get latest certificate check for each node
    nodes_data = []
    for node in nodes:
        # Get latest check for this node
        check_result = await db.execute(
            select(CertificateCheck)
            .where(CertificateCheck.node_id == node.id)
            .order_by(CertificateCheck.checked_at.desc())
            .limit(1)
        )
        cert_check = check_result.scalar_one_or_none()
        
        node_data = {
            'id': node.id,
            'display_name': node.display_name,
            'ip_address': node.ip_address,
            'maintenance_mode': node.maintenance_mode,
            'last_seen_at': node.last_seen_at,
            'cert_expiry_date': cert_check.cert_expiry_date if cert_check else None,
            'days_remaining': cert_check.days_remaining if cert_check else None,
            'check_status': cert_check.check_status if cert_check else 'never_checked',
            'checked_at': cert_check.checked_at if cert_check else None,
            'error_message': cert_check.error_message if cert_check else None
        }
        nodes_data.append(node_data)
    
    # Calculate statistics
    stats = {
        'total_nodes': len(nodes_data),
        'certs_ok': sum(1 for n in nodes_data if n['days_remaining'] and n['days_remaining'] > 30),
        'certs_warning': sum(1 for n in nodes_data if n['days_remaining'] and 7 < n['days_remaining'] <= 30),
        'certs_critical': sum(1 for n in nodes_data if n['days_remaining'] and 0 < n['days_remaining'] <= 7),
        'certs_expired': sum(1 for n in nodes_data if n['days_remaining'] and n['days_remaining'] <= 0),
        'certs_error': sum(1 for n in nodes_data if n['check_status'] not in ['success', 'never_checked'])
    }
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "nodes": nodes_data,
            "stats": stats,
            "now": datetime.utcnow()
        }
    )


# === API Endpoints ===

@app.get("/api/nodes", response_model=List[TransportNodeSchema])
async def get_nodes(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Get list of transport nodes."""
    query = select(TransportNode)
    if active_only:
        query = query.where(TransportNode.is_active == True)
    query = query.order_by(TransportNode.display_name)
    
    result = await db.execute(query)
    nodes = result.scalars().all()
    return nodes


@app.get("/api/nodes/{node_id}", response_model=NodeDetailSchema)
async def get_node_detail(node_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed information about a specific node."""
    # Get node
    result = await db.execute(
        select(TransportNode).where(TransportNode.id == node_id)
    )
    node = result.scalar_one_or_none()
    
    if not node:
        return {"error": "Node not found"}, 404
    
    # Get latest certificate check
    result = await db.execute(
        select(CertificateCheck)
        .where(CertificateCheck.node_id == node_id)
        .order_by(CertificateCheck.checked_at.desc())
        .limit(1)
    )
    latest_check = result.scalar_one_or_none()
    
    return {
        "node": node,
        "latest_cert_check": latest_check
    }


@app.get("/api/nodes/{node_id}/checks", response_model=List[CertificateCheckSchema])
async def get_node_checks(
    node_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Get certificate check history for a node."""
    result = await db.execute(
        select(CertificateCheck)
        .where(CertificateCheck.node_id == node_id)
        .order_by(CertificateCheck.checked_at.desc())
        .limit(limit)
    )
    checks = result.scalars().all()
    return checks


@app.get("/api/events", response_model=List[NodeEventSchema])
async def get_events(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Get recent node events."""
    result = await db.execute(
        select(NodeEvent)
        .order_by(NodeEvent.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return events


@app.get("/api/stats", response_model=DashboardStatsSchema)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics."""
    
    # Count nodes
    total_result = await db.execute(select(func.count(TransportNode.id)))
    total_nodes = total_result.scalar()
    
    active_result = await db.execute(
        select(func.count(TransportNode.id))
        .where(TransportNode.is_active == True)
    )
    active_nodes = active_result.scalar()
    
    # Get latest checks for active nodes
    query = (
        select(CertificateCheck)
        .join(TransportNode, CertificateCheck.node_id == TransportNode.id)
        .where(TransportNode.is_active == True)
        .where(CertificateCheck.check_status == 'success')
        .order_by(CertificateCheck.checked_at.desc())
    )
    result = await db.execute(query)
    checks = result.scalars().all()
    
    # Get unique latest check per node
    node_latest = {}
    for check in checks:
        if check.node_id not in node_latest:
            node_latest[check.node_id] = check
    
    # Count by expiry status
    certs_expiring_soon = sum(
        1 for c in node_latest.values()
        if c.days_remaining is not None and 7 < c.days_remaining <= 30
    )
    certs_expiring_very_soon = sum(
        1 for c in node_latest.values()
        if c.days_remaining is not None and 0 < c.days_remaining <= 7
    )
    certs_expired = sum(
        1 for c in node_latest.values()
        if c.days_remaining is not None and c.days_remaining <= 0
    )
    
    # Get last check times
    last_cert_check = max((c.checked_at for c in checks), default=None)
    
    # Get last NSX sync (last time a node was updated)
    last_update_result = await db.execute(
        select(func.max(TransportNode.last_seen_at))
    )
    last_nsx_sync = last_update_result.scalar()
    
    return {
        "total_nodes": total_nodes,
        "active_nodes": active_nodes,
        "inactive_nodes": total_nodes - active_nodes,
        "certs_expiring_soon": certs_expiring_soon,
        "certs_expiring_very_soon": certs_expiring_very_soon,
        "certs_expired": certs_expired,
        "last_nsx_sync": last_nsx_sync,
        "last_cert_check": last_cert_check
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "scheduler_running": scheduler_service is not None
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        reload=False
    )

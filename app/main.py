"""FastAPI application for ETN certificate monitoring with Keycloak auth."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, Depends, Request, HTTPException, status, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
from app.keycloak_auth import (
    get_current_active_user,
    get_current_user_from_cookie,
    login_user,
    refresh_token as refresh_keycloak_token,
    logout_user,
    KeycloakUser,
    exchange_code_for_token,
    KEYCLOAK_ENABLED
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler_service: Optional[SchedulerService] = None


# ============ PYDANTIC MODELS ============

class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: Optional[int] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ============ LIFESPAN MANAGER ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    global scheduler_service
    
    # Startup
    logger.info("Starting ETN Certificate Monitor...")
    
    if KEYCLOAK_ENABLED:
        logger.info("🔐 Keycloak authentication ENABLED")
    else:
        logger.warning("⚠️ Keycloak authentication DISABLED - running in open mode")
    
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
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates
templates = Jinja2Templates(directory="templates")


# ============ AUTHENTICATION ENDPOINTS ============

@app.post("/api/login", response_model=Token)
async def login(user_login: UserLogin):
    """Вход в систему через Keycloak"""
    if not KEYCLOAK_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak authentication is not enabled"
        )
    
    try:
        token_data = login_user(user_login.username, user_login.password)
        return token_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )


@app.post("/api/refresh", response_model=Token)
async def refresh(refresh_request: RefreshTokenRequest):
    """Обновление токена"""
    if not KEYCLOAK_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak authentication is not enabled"
        )
    
    try:
        token_data = refresh_keycloak_token(refresh_request.refresh_token)
        return token_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token refresh"
        )


@app.post("/api/logout")
async def logout(
    response: Response,
    refresh_request: RefreshTokenRequest = None,
    current_user: KeycloakUser = Depends(get_current_active_user) if KEYCLOAK_ENABLED else None
):
    """Выход из системы"""
    if not KEYCLOAK_ENABLED:
        return {"message": "Keycloak authentication is not enabled"}
    
    try:
        if refresh_request:
            logout_user(refresh_request.refresh_token)
        
        # Удаляем cookies
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")
        
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return {"message": "Logged out (with warnings)"}


@app.get("/api/verify")
async def verify_token(current_user: KeycloakUser = Depends(get_current_user_from_cookie) if KEYCLOAK_ENABLED else None):
    """Проверка токена из cookie"""
    if not KEYCLOAK_ENABLED:
        return {
            "valid": True,
            "username": "anonymous",
            "email": None,
            "roles": [],
            "auth_disabled": True
        }
    
    return {
        "valid": True,
        "username": current_user.username,
        "email": current_user.email,
        "roles": current_user.roles
    }


@app.get("/api/callback")
async def keycloak_callback(code: str = Query(...), response: Response):
    """
    Обмен code на token после редиректа от Keycloak.
    Устанавливает токен в HTTP-only cookie и редиректит на главную страницу.
    """
    if not KEYCLOAK_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak authentication is not enabled"
        )
    
    try:
        token_data = exchange_code_for_token(code)
        
        # ✅ Устанавливаем токен в HTTP-only cookie
        response.set_cookie(
            key="access_token",
            value=token_data["access_token"],
            httponly=True,
            secure=True,  # Только для HTTPS
            samesite="lax",
            max_age=token_data.get("expires_in", 3600)
        )
        
        if token_data.get("refresh_token"):
            response.set_cookie(
                key="refresh_token",
                value=token_data["refresh_token"],
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=86400  # 24 hours
            )
        
        logger.info("Token set in cookie, redirecting to dashboard")
        
        # ✅ Редиректим на главную страницу
        return RedirectResponse(url="/", status_code=302)
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Authorization failed",
            headers={"Location": "/login?error=auth_failed"}
        )


# ============ WEB UI ENDPOINTS ============

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page with Keycloak SSO button"""
    if not KEYCLOAK_ENABLED:
        # Если Keycloak отключен, редиректим сразу на главную
        return RedirectResponse(url="/")
    
    html_path = Path(__file__).parent.parent / "templates" / "login.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<h1>Login page not found</h1>", status_code=404)


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    current_user: KeycloakUser = Depends(get_current_user_from_cookie) if KEYCLOAK_ENABLED else None
):
    """Main dashboard page with cookie-based authentication."""
    
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
    
    # Pass user info to template
    user_info = {
        'username': current_user.username if current_user else 'anonymous',
        'email': current_user.email if current_user else None
    }
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "nodes": nodes_data,
            "stats": stats,
            "now": datetime.utcnow(),
            "user": user_info,
            "keycloak_enabled": KEYCLOAK_ENABLED
        }
    )


# ============ API ENDPOINTS (Protected if Keycloak enabled) ============

def optional_auth():
    """Optional authentication dependency for API"""
    if KEYCLOAK_ENABLED:
        return Depends(get_current_active_user)
    return None


@app.get("/api/nodes", response_model=List[TransportNodeSchema])
async def get_nodes(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: KeycloakUser = optional_auth()
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
async def get_node_detail(
    node_id: str, 
    db: AsyncSession = Depends(get_db),
    current_user: KeycloakUser = optional_auth()
):
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
    db: AsyncSession = Depends(get_db),
    current_user: KeycloakUser = optional_auth()
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
async def get_events(
    limit: int = 100, 
    db: AsyncSession = Depends(get_db),
    current_user: KeycloakUser = optional_auth()
):
    """Get recent node events."""
    result = await db.execute(
        select(NodeEvent)
        .order_by(NodeEvent.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return events


@app.get("/api/stats", response_model=DashboardStatsSchema)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: KeycloakUser = optional_auth()
):
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
        "scheduler_running": scheduler_service is not None,
        "keycloak_enabled": KEYCLOAK_ENABLED
    }


@app.post("/api/trigger/cert-check")
async def trigger_cert_check(
    current_user: KeycloakUser = optional_auth()
):
    """Manually trigger certificate check."""
    if scheduler_service:
        logger.info("Manual certificate check triggered via API")
        asyncio.create_task(scheduler_service.check_certificates())
        return {
            "status": "triggered",
            "message": "Certificate check started in background",
            "timestamp": datetime.utcnow().isoformat()
        }
    return {
        "status": "error",
        "message": "Scheduler not running"
    }, 503


@app.post("/api/trigger/nsx-sync")
async def trigger_nsx_sync(
    current_user: KeycloakUser = optional_auth()
):
    """Manually trigger NSX sync."""
    if scheduler_service:
        logger.info("Manual NSX sync triggered via API")
        asyncio.create_task(scheduler_service.sync_nsx_nodes())
        return {
            "status": "triggered",
            "message": "NSX sync started in background",
            "timestamp": datetime.utcnow().isoformat()
        }
    return {
        "status": "error",
        "message": "Scheduler not running"
    }, 503


@app.get("/api/scheduler/status")
async def scheduler_status(
    current_user: KeycloakUser = optional_auth()
):
    """Get scheduler status and next run times."""
    if not scheduler_service:
        return {"status": "error", "message": "Scheduler not running"}, 503
    
    jobs_info = []
    for job in scheduler_service.scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return {
        "status": "running",
        "jobs": jobs_info,
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        reload=False
    )
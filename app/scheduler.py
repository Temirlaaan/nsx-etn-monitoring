"""Background scheduler for periodic tasks."""
import asyncio
import logging
from datetime import datetime
from typing import List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.database import AsyncSessionLocal
from app.models import TransportNode, CertificateCheck, NodeEvent
from app.nsx_client import NSXClient
from app.ssh_checker import CertificateChecker
from app.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manage scheduled background tasks."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.nsx_client = NSXClient()
        self.cert_checker = CertificateChecker()
        self.telegram = TelegramNotifier()
        
    def start(self):
        """Start the scheduler with configured jobs."""
        
        # Job 1: Sync ETN from NSX (every 2 days)
        self.scheduler.add_job(
            self.sync_nsx_nodes,
            trigger=CronTrigger.from_crontab(config.NSX_CHECK_CRON),
            id='sync_nsx_nodes',
            name='Sync ETN from NSX-T Manager',
            replace_existing=True
        )
        
        # Job 2: Check certificates (every week)
        self.scheduler.add_job(
            self.check_certificates,
            trigger=CronTrigger.from_crontab(config.CERT_CHECK_CRON),
            id='check_certificates',
            name='Check ETN SSL Certificates',
            replace_existing=True
        )
        
        # Job 3: Send Telegram notifications (daily at 10:00)
        self.scheduler.add_job(
            self.send_expiry_notifications,
            trigger=CronTrigger(hour=10, minute=0),
            id='send_notifications',
            name='Send Certificate Expiry Notifications',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Scheduler started with jobs:")
        for job in self.scheduler.get_jobs():
            logger.info(f"  - {job.name}: {job.trigger}")
    
    def shutdown(self):
        """Shutdown the scheduler."""
        self.scheduler.shutdown()
        self.nsx_client.close()
        logger.info("Scheduler stopped")
    
    async def sync_nsx_nodes(self):
        """Sync Edge Transport Nodes from NSX-T Manager."""
        logger.info("Starting NSX ETN synchronization...")
        
        try:
            # Get current ETN from NSX
            nsx_nodes = self.nsx_client.get_edge_transport_nodes()
            
            if not nsx_nodes:
                logger.warning("No ETN retrieved from NSX")
                return
            
            async with AsyncSessionLocal() as db:
                # Get existing nodes from DB
                result = await db.execute(select(TransportNode))
                existing_nodes = {node.id: node for node in result.scalars().all()}
                
                nsx_node_ids = {node['node_id'] for node in nsx_nodes}
                existing_node_ids = set(existing_nodes.keys())
                
                # Find new nodes
                new_node_ids = nsx_node_ids - existing_node_ids
                # Find removed nodes
                removed_node_ids = existing_node_ids - nsx_node_ids
                # Find reappeared nodes (was inactive, now active again)
                reappeared_node_ids = {
                    nid for nid in nsx_node_ids 
                    if nid in existing_nodes and not existing_nodes[nid].is_active
                }
                
                new_nodes = []
                
                # Add new nodes
                for node in nsx_nodes:
                    node_id = node['node_id']
                    
                    if node_id in new_node_ids:
                        # Brand new node
                        db_node = TransportNode(
                            id=node_id,
                            display_name=node['display_name'],
                            ip_address=node['ip_address'],
                            maintenance_mode=node['maintenance_mode'],
                            first_seen_at=datetime.utcnow(),
                            last_seen_at=datetime.utcnow(),
                            is_active=True
                        )
                        db.add(db_node)
                        new_nodes.append(db_node)
                        
                        # Log event
                        event = NodeEvent(
                            node_id=node_id,
                            event_type='added',
                            display_name=node['display_name'],
                            ip_address=node['ip_address']
                        )
                        db.add(event)
                        logger.info(f"New ETN discovered: {node['display_name']} ({node['ip_address']})")
                        
                    elif node_id in reappeared_node_ids:
                        # Node came back
                        existing_node = existing_nodes[node_id]
                        existing_node.is_active = True
                        existing_node.last_seen_at = datetime.utcnow()
                        existing_node.ip_address = node['ip_address']
                        existing_node.display_name = node['display_name']
                        existing_node.maintenance_mode = node['maintenance_mode']
                        
                        event = NodeEvent(
                            node_id=node_id,
                            event_type='reappeared',
                            display_name=node['display_name'],
                            ip_address=node['ip_address']
                        )
                        db.add(event)
                        logger.info(f"ETN reappeared: {node['display_name']}")
                        
                    else:
                        # Update existing node
                        existing_node = existing_nodes[node_id]
                        existing_node.last_seen_at = datetime.utcnow()
                        existing_node.ip_address = node['ip_address']
                        existing_node.display_name = node['display_name']
                        existing_node.maintenance_mode = node['maintenance_mode']
                
                # Mark removed nodes as inactive
                removed_nodes = []
                for node_id in removed_node_ids:
                    node = existing_nodes[node_id]
                    node.is_active = False
                    removed_nodes.append(node)
                    
                    event = NodeEvent(
                        node_id=node_id,
                        event_type='removed',
                        display_name=node.display_name,
                        ip_address=node.ip_address
                    )
                    db.add(event)
                    logger.warning(f"ETN removed from NSX: {node.display_name}")
                
                await db.commit()
                
                logger.info(
                    f"NSX sync completed: {len(new_nodes)} new, "
                    f"{len(reappeared_node_ids)} reappeared, "
                    f"{len(removed_nodes)} removed"
                )
                
                # Send Telegram notifications
                if new_nodes:
                    await self.telegram.notify_new_nodes(new_nodes)
                if removed_nodes:
                    await self.telegram.notify_removed_nodes(removed_nodes)
                
        except Exception as e:
            logger.error(f"Error syncing NSX nodes: {str(e)}", exc_info=True)
    
    async def check_certificates(self):
        """Check SSL certificates on all active ETN."""
        logger.info("Starting certificate checks...")
        
        try:
            async with AsyncSessionLocal() as db:
                # Get all active nodes
                result = await db.execute(
                    select(TransportNode).where(TransportNode.is_active == True)
                )
                nodes = result.scalars().all()
                
                if not nodes:
                    logger.warning("No active ETN found in database")
                    return
                
                # Prepare host list for parallel checking
                hosts = [
                    {'host': node.ip_address, 'node_id': node.id}
                    for node in nodes
                ]
                
                # Check certificates in parallel
                check_results = await self.cert_checker.check_multiple_certificates(hosts)
                
                # Save results to database
                for result in check_results:
                    check_record = CertificateCheck(
                        node_id=result['node_id'],
                        cert_expiry_date=result['cert_expiry_date'],
                        days_remaining=result['days_remaining'] if result['cert_expiry_date'] else -999,
                        check_status=result['status'],
                        error_message=result.get('error_message')
                    )
                    db.add(check_record)
                
                await db.commit()
                
                # Log summary
                success_count = sum(1 for r in check_results if r['status'] == 'success')
                logger.info(
                    f"Certificate check completed: {success_count}/{len(check_results)} successful"
                )
                
                # Send notifications for expiring certs
                await self.telegram.check_and_notify_expiring_certs(db)
                
        except Exception as e:
            logger.error(f"Error checking certificates: {str(e)}", exc_info=True)
    
    async def send_expiry_notifications(self):
        """Send Telegram notifications for expiring certificates."""
        logger.info("Checking for expiring certificates...")
        
        try:
            async with AsyncSessionLocal() as db:
                await self.telegram.check_and_notify_expiring_certs(db)
        except Exception as e:
            logger.error(f"Error sending notifications: {str(e)}", exc_info=True)
    
    async def run_initial_sync(self):
        """Run initial sync on startup."""
        logger.info("Running initial NSX sync on startup...")
        await self.sync_nsx_nodes()
        
        # ✅ ДОБАВЛЕНО: Запустить проверку сертификатов сразу после синхронизации
        logger.info("Running initial certificate check on startup...")
        await self.check_certificates()
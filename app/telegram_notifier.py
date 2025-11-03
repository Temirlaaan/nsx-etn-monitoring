"""Telegram notification service."""
import logging
from datetime import datetime, date
from typing import List
from telegram import Bot
from telegram.error import TelegramError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models import TransportNode, CertificateCheck, TelegramNotification

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications to Telegram."""
    
    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.bot = None
        
        if self.bot_token and self.chat_id:
            self.bot = Bot(token=self.bot_token)
            logger.info("Telegram bot initialized")
        else:
            logger.warning("Telegram bot token or chat ID not configured")
    
    async def send_message(self, message: str) -> bool:
        """
        Send a message to Telegram.
        
        Args:
            message: Text to send
            
        Returns:
            True if sent successfully
        """
        if not self.bot:
            logger.warning("Telegram bot not configured, skipping notification")
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            logger.info("Telegram notification sent successfully")
            return True
            
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {str(e)}", exc_info=True)
            return False
    
    async def check_and_notify_expiring_certs(self, db: AsyncSession):
        """
        Check for expiring certificates and send notifications.
        
        Args:
            db: Database session
        """
        if not self.bot:
            logger.info("Telegram not configured, skipping certificate expiry notifications")
            return
        
        logger.info("Checking for expiring certificates...")
        
        # Get all active nodes with their latest certificate check
        query = (
            select(TransportNode, CertificateCheck)
            .join(CertificateCheck, TransportNode.id == CertificateCheck.node_id)
            .where(TransportNode.is_active == True)
            .where(CertificateCheck.check_status == 'success')
            .order_by(CertificateCheck.checked_at.desc())
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        # Get latest check for each node
        node_latest_checks = {}
        for node, check in rows:
            if node.id not in node_latest_checks:
                node_latest_checks[node.id] = (node, check)
        
        # Group by warning levels
        expiring_soon = []  # < 30 days
        expiring_very_soon = []  # < 7 days
        expired = []  # <= 0 days
        
        for node, check in node_latest_checks.values():
            days = check.days_remaining
            
            if days <= 0:
                expired.append((node, check))
            elif days <= 7:
                expiring_very_soon.append((node, check))
            elif days <= config.CERT_WARNING_DAYS:
                expiring_soon.append((node, check))
        
        # Send notifications
        today_str = date.today().isoformat()
        
        if expired:
            await self._send_cert_notifications(
                db, expired, 'cert_expired', today_str,
                '🔴 <b>КРИТИЧНО: Сертификаты истекли!</b>'
            )
        
        if expiring_very_soon:
            await self._send_cert_notifications(
                db, expiring_very_soon, 'cert_expiring_7d', today_str,
                '🟠 <b>ВНИМАНИЕ: Сертификаты истекают через 7 дней!</b>'
            )
        
        if expiring_soon:
            await self._send_cert_notifications(
                db, expiring_soon, 'cert_expiring_30d', today_str,
                '🟡 <b>Предупреждение: Сертификаты истекают в течение 30 дней</b>'
            )
        
        if not (expired or expiring_very_soon or expiring_soon):
            logger.info("No expiring certificates found")
    
    async def _send_cert_notifications(
        self,
        db: AsyncSession,
        nodes_checks: List,
        notification_type: str,
        today_str: str,
        title: str
    ):
        """Send notifications for a group of certificates."""
        
        # Filter nodes that haven't been notified today
        to_notify = []
        for node, check in nodes_checks:
            # Check if already notified today
            query = select(TelegramNotification).where(
                TelegramNotification.node_id == node.id,
                TelegramNotification.notification_type == notification_type,
                TelegramNotification.notification_date == today_str
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()
            
            if not existing:
                to_notify.append((node, check))
        
        if not to_notify:
            logger.info(f"No new {notification_type} notifications to send")
            return
        
        # Build message
        message_lines = [title, '']
        
        for node, check in to_notify:
            days = check.days_remaining
            expiry_date = check.cert_expiry_date.strftime('%Y-%m-%d')
            
            if days <= 0:
                days_text = f"<b>ИСТЁК {abs(days)} дней назад</b>"
            else:
                days_text = f"{days} дней"
            
            message_lines.append(
                f"• <b>{node.display_name}</b> ({node.ip_address})\n"
                f"  Истекает: {expiry_date} ({days_text})"
            )
        
        message = '\n'.join(message_lines)
        
        # Send notification
        sent = await self.send_message(message)
        
        # Record notifications in database
        if sent:
            for node, check in to_notify:
                notification = TelegramNotification(
                    node_id=node.id,
                    notification_type=notification_type,
                    notification_date=today_str
                )
                db.add(notification)
            
            await db.commit()
            logger.info(f"Sent {notification_type} notification for {len(to_notify)} nodes")
    
    async def notify_new_nodes(self, new_nodes: List[TransportNode]):
        """
        Send notification about newly discovered nodes.
        
        Args:
            new_nodes: List of newly added TransportNode objects
        """
        if not new_nodes or not self.bot:
            return
        
        message_lines = ['🆕 <b>Обнаружены новые Edge Transport Nodes:</b>', '']
        
        for node in new_nodes:
            message_lines.append(
                f"• <b>{node.display_name}</b>\n"
                f"  IP: {node.ip_address}\n"
                f"  ID: {node.id}"
            )
        
        message = '\n'.join(message_lines)
        await self.send_message(message)
    
    async def notify_removed_nodes(self, removed_nodes: List[TransportNode]):
        """
        Send notification about removed nodes.
        
        Args:
            removed_nodes: List of removed TransportNode objects
        """
        if not removed_nodes or not self.bot:
            return
        
        message_lines = ['❌ <b>Edge Transport Nodes удалены из NSX:</b>', '']
        
        for node in removed_nodes:
            message_lines.append(
                f"• <b>{node.display_name}</b>\n"
                f"  IP: {node.ip_address}"
            )
        
        message = '\n'.join(message_lines)
        await self.send_message(message)

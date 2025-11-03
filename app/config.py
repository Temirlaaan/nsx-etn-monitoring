"""Configuration management from environment variables."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class Config:
    """Application configuration."""
    
    # NSX-T Manager
    NSX_MANAGER_URL: str = os.getenv('NSX_MANAGER_URL', 'https://nsx01cast.t-cloud.kz')
    NSX_USERNAME: str = os.getenv('NSX_USERNAME', '')
    NSX_PASSWORD: str = os.getenv('NSX_PASSWORD', '')
    
    # ETN SSH
    ETN_SSH_USERNAME: str = os.getenv('ETN_SSH_USERNAME', '')
    ETN_SSH_PASSWORD: str = os.getenv('ETN_SSH_PASSWORD', '')
    ETN_SSH_PORT: int = int(os.getenv('ETN_SSH_PORT', '22'))
    ETN_SSH_TIMEOUT: int = 30  # seconds
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID: str = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # Scheduler (cron expressions)
    NSX_CHECK_CRON: str = os.getenv('NSX_CHECK_CRON', '0 2 */2 * *')  # Every 2 days at 02:00
    CERT_CHECK_CRON: str = os.getenv('CERT_CHECK_CRON', '0 3 * * 1')  # Every Monday at 03:00
    
    # Certificate warnings
    CERT_WARNING_DAYS: int = int(os.getenv('CERT_WARNING_DAYS', '30'))
    
    # Database
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./etn_monitor.db')
    
    # Web Server
    WEB_HOST: str = os.getenv('WEB_HOST', '0.0.0.0')
    WEB_PORT: int = int(os.getenv('WEB_PORT', '8000'))
    
    # ETN Filtering (optional - for testing specific nodes)
    ETN_WHITELIST: str = os.getenv('ETN_WHITELIST', '')  # Comma-separated IPs
    
    @classmethod
    def get_etn_whitelist(cls) -> list:
        """Get list of whitelisted ETN IPs."""
        if not cls.ETN_WHITELIST:
            return []
        return [ip.strip() for ip in cls.ETN_WHITELIST.split(',') if ip.strip()]
    
    @classmethod
    def validate(cls):
        """Validate required configuration."""
        required = [
            ('NSX_USERNAME', cls.NSX_USERNAME),
            ('NSX_PASSWORD', cls.NSX_PASSWORD),
            ('ETN_SSH_USERNAME', cls.ETN_SSH_USERNAME),
            ('ETN_SSH_PASSWORD', cls.ETN_SSH_PASSWORD),
        ]
        
        missing = [name for name, value in required if not value]
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")


# Global config instance
config = Config()

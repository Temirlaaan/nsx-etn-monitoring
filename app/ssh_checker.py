"""SSH certificate checker for ETN hosts."""
import asyncio
import asyncssh
import logging
from datetime import datetime
from typing import Dict, Optional
from app.config import config

logger = logging.getLogger(__name__)


class CertificateChecker:
    """Check SSL certificates on ETN hosts via SSH."""
    
    CERT_PATH = '/etc/vmware/nsx/host-cert.pem'
    OPENSSL_CMD = f'openssl x509 -enddate -noout -in {CERT_PATH}'
    
    def __init__(self):
        self.username = config.ETN_SSH_USERNAME
        self.password = config.ETN_SSH_PASSWORD
        self.port = config.ETN_SSH_PORT
        self.timeout = config.ETN_SSH_TIMEOUT
    
    async def check_certificate(self, host: str, node_id: str) -> Dict:
        """
        Check certificate expiration date on a single host.
        
        Args:
            host: IP address or hostname
            node_id: Node ID for logging
            
        Returns:
            Dict with check results
        """
        result = {
            'node_id': node_id,
            'host': host,
            'status': 'error',
            'cert_expiry_date': None,
            'days_remaining': None,
            'error_message': None
        }
        
        try:
            logger.debug(f"Connecting to {host} (node: {node_id})...")
            
            async with asyncssh.connect(
                host,
                username=self.username,
                password=self.password,
                port=self.port,
                known_hosts=None,  # Don't check host keys
                connect_timeout=self.timeout,
                login_timeout=self.timeout
            ) as conn:
                
                # Execute openssl command
                ssh_result = await conn.run(self.OPENSSL_CMD, check=False, timeout=10)
                
                if ssh_result.exit_status != 0:
                    error_msg = f"Command failed: {ssh_result.stderr}"
                    logger.error(f"Failed to read certificate on {host}: {error_msg}")
                    result['error_message'] = error_msg
                    result['status'] = 'error'
                    return result
                
                # Parse output: "notAfter=Dec 31 23:59:59 2025 GMT"
                output = ssh_result.stdout.strip()
                expiry_date = self._parse_cert_date(output)
                
                if expiry_date:
                    days_remaining = (expiry_date - datetime.utcnow()).days
                    result.update({
                        'status': 'success',
                        'cert_expiry_date': expiry_date,
                        'days_remaining': days_remaining
                    })
                    logger.info(f"Certificate on {host} expires in {days_remaining} days ({expiry_date.date()})")
                else:
                    result['error_message'] = f"Failed to parse date from: {output}"
                    result['status'] = 'error'
                    logger.error(f"Failed to parse certificate date on {host}: {output}")
                
        except asyncssh.Error as e:
            error_msg = f"SSH connection error: {str(e)}"
            logger.error(f"SSH error for {host}: {error_msg}")
            result['error_message'] = error_msg
            result['status'] = 'ssh_failed'
            
        except asyncio.TimeoutError:
            error_msg = f"Connection timeout after {self.timeout}s"
            logger.error(f"Timeout connecting to {host}")
            result['error_message'] = error_msg
            result['status'] = 'timeout'
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Unexpected error checking {host}: {error_msg}", exc_info=True)
            result['error_message'] = error_msg
            result['status'] = 'error'
        
        return result
    
    def _parse_cert_date(self, openssl_output: str) -> Optional[datetime]:
        """
        Parse certificate date from openssl output.
        
        Args:
            openssl_output: String like "notAfter=Dec 31 23:59:59 2025 GMT"
            
        Returns:
            datetime object or None
        """
        try:
            # Extract date part after "notAfter="
            if 'notAfter=' in openssl_output:
                date_str = openssl_output.split('notAfter=')[1].strip()
            else:
                date_str = openssl_output.strip()
            
            # Parse date: "Dec 31 23:59:59 2025 GMT"
            # Format: %b %d %H:%M:%S %Y %Z
            date_obj = datetime.strptime(date_str, '%b %d %H:%M:%S %Y %Z')
            return date_obj
            
        except Exception as e:
            logger.error(f"Failed to parse date '{openssl_output}': {str(e)}")
            return None
    
    async def check_multiple_certificates(self, hosts: list) -> list:
        """
        Check certificates on multiple hosts in parallel.
        
        Args:
            hosts: List of dicts with 'host' and 'node_id' keys
            
        Returns:
            List of check results
        """
        logger.info(f"Starting certificate checks for {len(hosts)} hosts...")
        
        tasks = [
            self.check_certificate(host_info['host'], host_info['node_id'])
            for host_info in hosts
        ]
        
        # Run all checks in parallel with return_exceptions to handle failures gracefully
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any unexpected exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                host_info = hosts[i]
                logger.error(f"Unhandled exception for {host_info['host']}: {str(result)}")
                processed_results.append({
                    'node_id': host_info['node_id'],
                    'host': host_info['host'],
                    'status': 'error',
                    'error_message': f"Unhandled exception: {str(result)}"
                })
            else:
                processed_results.append(result)
        
        # Log summary
        success_count = sum(1 for r in processed_results if r['status'] == 'success')
        logger.info(f"Certificate check completed: {success_count}/{len(hosts)} successful")
        
        return processed_results

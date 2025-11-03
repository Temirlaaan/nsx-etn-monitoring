"""NSX-T Manager API client."""
import requests
import logging
from typing import List, Dict, Optional
from requests.auth import HTTPBasicAuth
from app.config import config

logger = logging.getLogger(__name__)


class NSXClient:
    """Client for NSX-T Manager API."""
    
    def __init__(self):
        self.base_url = config.NSX_MANAGER_URL.rstrip('/')
        self.username = config.NSX_USERNAME
        self.password = config.NSX_PASSWORD
        self.session = None
        self.cookies = {}
        
    def _get_session(self) -> requests.Session:
        """Get or create authenticated session."""
        if self.session is None:
            self.session = requests.Session()
            self.session.verify = False  # Disable SSL verification as requested
            
            # Disable SSL warnings
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Authentication using form data (as per NSX-T requirements)
            auth_url = f"{self.base_url}/api/session/create"
            
            # Prepare form data
            auth_data = {
                'j_username': self.username,
                'j_password': self.password
            }
            
            # Set headers
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            response = self.session.post(
                auth_url,
                data=auth_data,
                headers=headers,
                auth=HTTPBasicAuth(self.username, self.password),
                verify=False
            )
            
            if response.status_code == 200:
                # Extract X-XSRF-TOKEN from response headers
                xsrf_token = response.headers.get('X-XSRF-TOKEN')
                
                if xsrf_token:
                    self.cookies = {
                        'X-XSRF-TOKEN': xsrf_token
                    }
                    logger.info("Successfully authenticated to NSX-T Manager")
                    logger.debug(f"X-XSRF-TOKEN: {xsrf_token[:20]}...")
                else:
                    logger.warning("No X-XSRF-TOKEN in response, trying to continue...")
                    self.cookies = {}
            else:
                logger.error(f"Authentication failed: {response.status_code} - {response.text}")
                raise Exception(f"Failed to authenticate to NSX-T Manager: {response.status_code}")
                
        return self.session
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make authenticated request to NSX API."""
        session = self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        # Set default headers
        headers = kwargs.get('headers', {})
        
        # Add Content-Type for API requests
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'
        
        # Add XSRF token to headers if available
        if self.cookies.get('X-XSRF-TOKEN'):
            headers['X-XSRF-TOKEN'] = self.cookies['X-XSRF-TOKEN']
        
        kwargs['headers'] = headers
        
        response = session.request(method, url, **kwargs)
        
        # Handle session expiration
        if response.status_code == 403:
            logger.warning("Session expired, re-authenticating...")
            self.session = None
            self.cookies = {}
            return self._make_request(method, endpoint, **kwargs)
            
        return response
    
    def get_transport_nodes(self) -> List[Dict]:
        """
        Get all transport nodes from NSX-T Manager.
        
        Returns:
            List of transport node dictionaries
        """
        try:
            response = self._make_request('GET', '/api/v1/transport-nodes')
            
            if response.status_code == 200:
                data = response.json()
                all_nodes = data.get('results', [])
                logger.info(f"Retrieved {len(all_nodes)} transport nodes from NSX")
                return all_nodes
            else:
                logger.error(f"Failed to get transport nodes: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting transport nodes: {str(e)}", exc_info=True)
            return []
    
    def get_edge_transport_nodes(self) -> List[Dict]:
        """
        Get only Edge Transport Nodes (ETN) from NSX-T Manager.
        
        Returns:
            List of edge transport node dictionaries with extracted info
        """
        all_nodes = self.get_transport_nodes()
        
        # Get whitelist from config
        whitelist = config.get_etn_whitelist()
        if whitelist:
            logger.info(f"ETN Whitelist enabled: {whitelist}")
        
        edge_nodes = []
        for node in all_nodes:
            node_deployment = node.get('node_deployment_info', {})
            
            # Filter only EdgeNode types
            if node_deployment.get('resource_type') == 'EdgeNode':
                ip_addresses = node_deployment.get('ip_addresses', [])
                ip_address = ip_addresses[0] if ip_addresses else None
                
                # Apply whitelist filter if configured
                if whitelist and ip_address not in whitelist:
                    logger.debug(f"Skipping {node.get('display_name')} ({ip_address}) - not in whitelist")
                    continue
                
                edge_node = {
                    'node_id': node.get('id'),
                    'display_name': node.get('display_name'),
                    'ip_address': ip_address,
                    'maintenance_mode': node.get('maintenance_mode', 'UNKNOWN'),
                    'hostname': node_deployment.get('node_settings', {}).get('hostname'),
                }
                
                if edge_node['ip_address']:  # Only add if has IP
                    edge_nodes.append(edge_node)
        
        if whitelist:
            logger.info(f"Filtered {len(edge_nodes)} Edge Transport Nodes (whitelist applied)")
        else:
            logger.info(f"Filtered {len(edge_nodes)} Edge Transport Nodes")
        return edge_nodes
    
    def close(self):
        """Close the session."""
        if self.session:
            self.session.close()
            self.session = None

#!/usr/bin/env python3
"""Test connection to NSX-T Manager and ETN hosts."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import config
from app.nsx_client import NSXClient
from app.ssh_checker import CertificateChecker


async def test_nsx_connection():
    """Test NSX-T Manager API connection."""
    print("=" * 60)
    print("Testing NSX-T Manager Connection")
    print("=" * 60)
    print(f"URL: {config.NSX_MANAGER_URL}")
    print(f"Username: {config.NSX_USERNAME}")
    print()
    
    try:
        client = NSXClient()
        
        # Test getting all transport nodes
        print("Fetching transport nodes...")
        all_nodes = client.get_transport_nodes()
        print(f"✅ Total transport nodes: {len(all_nodes)}")
        
        # Test filtering edge nodes
        print("\nFetching Edge Transport Nodes...")
        edge_nodes = client.get_edge_transport_nodes()
        print(f"✅ Edge Transport Nodes found: {len(edge_nodes)}")
        
        if edge_nodes:
            print("\nEdge Transport Nodes:")
            for node in edge_nodes[:5]:  # Show first 5
                print(f"  • {node['display_name']} - {node['ip_address']} [{node['maintenance_mode']}]")
            
            if len(edge_nodes) > 5:
                print(f"  ... and {len(edge_nodes) - 5} more")
        
        client.close()
        return edge_nodes
        
    except Exception as e:
        print(f"❌ Error connecting to NSX: {str(e)}")
        return []


async def test_ssh_connection(edge_nodes):
    """Test SSH connection to ETN hosts."""
    if not edge_nodes:
        print("\n⚠️  No edge nodes to test SSH connection")
        return
    
    print("\n" + "=" * 60)
    print("Testing SSH Connection to ETN Hosts")
    print("=" * 60)
    print(f"Username: {config.ETN_SSH_USERNAME}")
    print(f"Port: {config.ETN_SSH_PORT}")
    print()
    
    checker = CertificateChecker()
    
    # Test first 3 nodes
    test_nodes = edge_nodes[:3]
    print(f"Testing SSH on {len(test_nodes)} nodes...\n")
    
    hosts = [
        {'host': node['ip_address'], 'node_id': node['node_id']}
        for node in test_nodes
    ]
    
    results = await checker.check_multiple_certificates(hosts)
    
    print("\nResults:")
    success_count = 0
    for result in results:
        node = next(n for n in test_nodes if n['node_id'] == result['node_id'])
        status_icon = "✅" if result['status'] == 'success' else "❌"
        
        print(f"\n{status_icon} {node['display_name']} ({result['host']})")
        print(f"   Status: {result['status']}")
        
        if result['status'] == 'success':
            print(f"   Expiry: {result['cert_expiry_date']}")
            print(f"   Days remaining: {result['days_remaining']}")
            success_count += 1
        else:
            print(f"   Error: {result.get('error_message', 'Unknown error')}")
    
    print(f"\n{'=' * 60}")
    print(f"SSH Test Summary: {success_count}/{len(results)} successful")


async def test_telegram():
    """Test Telegram bot connection."""
    print("\n" + "=" * 60)
    print("Testing Telegram Bot Connection")
    print("=" * 60)
    
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("⚠️  Telegram not configured (optional)")
        print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env to enable")
        return
    
    print(f"Bot Token: {config.TELEGRAM_BOT_TOKEN[:20]}...")
    print(f"Chat ID: {config.TELEGRAM_CHAT_ID}")
    print()
    
    try:
        from app.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier()
        
        message = "🧪 Test message from ETN Certificate Monitor\nConnection successful!"
        success = await notifier.send_message(message)
        
        if success:
            print("✅ Telegram test message sent successfully!")
            print("   Check your Telegram to verify")
        else:
            print("❌ Failed to send Telegram message")
            
    except Exception as e:
        print(f"❌ Error testing Telegram: {str(e)}")


async def main():
    """Run all connection tests."""
    print("\n🔍 ETN Certificate Monitor - Connection Test")
    print()
    
    # Validate config
    try:
        config.validate()
        print("✅ Configuration validated\n")
    except ValueError as e:
        print(f"❌ Configuration error: {e}\n")
        print("Please check your .env file")
        return
    
    # Test NSX connection
    edge_nodes = await test_nsx_connection()
    
    # Test SSH connection
    if edge_nodes:
        await test_ssh_connection(edge_nodes)
    
    # Test Telegram
    await test_telegram()
    
    print("\n" + "=" * 60)
    print("✅ Connection tests completed!")
    print("=" * 60)
    print("\nIf all tests passed, you can start the service with:")
    print("  docker-compose up -d")
    print("\nOr run locally:")
    print("  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
    print()


if __name__ == "__main__":
    asyncio.run(main())

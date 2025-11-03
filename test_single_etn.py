#!/usr/bin/env python3
"""Test SSH connection and certificate check for a specific ETN host."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import config
from app.ssh_checker import CertificateChecker


async def test_single_etn(host: str):
    """Test SSH connection and certificate check for a single ETN."""
    print("=" * 70)
    print(f"🔍 Testing ETN: {host}")
    print("=" * 70)
    print()
    
    # Display configuration
    print("📋 Configuration:")
    print(f"  SSH Username: {config.ETN_SSH_USERNAME}")
    print(f"  SSH Port: {config.ETN_SSH_PORT}")
    print(f"  Timeout: {config.ETN_SSH_TIMEOUT}s")
    print(f"  Certificate Path: /etc/vmware/nsx/host-cert.pem")
    print()
    
    # Create checker
    checker = CertificateChecker()
    
    print(f"🔌 Connecting to {host}...")
    print()
    
    # Perform check
    result = await checker.check_certificate(host, node_id="test-node")
    
    # Display results
    print("=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    print()
    
    if result['status'] == 'success':
        print("✅ SUCCESS - Certificate check completed!")
        print()
        print(f"📅 Certificate Expiry Date: {result['cert_expiry_date']}")
        print(f"⏰ Expiry Time: {result['cert_expiry_date'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print()
        
        days = result['days_remaining']
        
        # Status indicator
        if days <= 0:
            status_emoji = "🔴"
            status_text = "EXPIRED"
        elif days <= 7:
            status_emoji = "🟠"
            status_text = "CRITICAL"
        elif days <= 30:
            status_emoji = "🟡"
            status_text = "WARNING"
        else:
            status_emoji = "🟢"
            status_text = "OK"
        
        print(f"{status_emoji} Status: {status_text}")
        print(f"📊 Days Remaining: {days} days")
        print()
        
        # Additional info
        if days <= 0:
            print(f"⚠️  Certificate EXPIRED {abs(days)} days ago!")
        elif days <= 7:
            print(f"⚠️  Certificate expires in less than a week!")
        elif days <= 30:
            print(f"⚠️  Certificate expires soon. Consider renewal.")
        else:
            print(f"✅ Certificate is valid for {days} more days.")
        
    else:
        print(f"❌ FAILED - Status: {result['status']}")
        print()
        print(f"Error Message: {result['error_message']}")
        print()
        
        # Troubleshooting tips
        print("🔧 Troubleshooting:")
        if result['status'] == 'ssh_failed':
            print("  • Check SSH credentials in .env file")
            print("  • Verify SSH service is running on the host")
            print("  • Check firewall rules")
            print(f"  • Try manual connection: ssh {config.ETN_SSH_USERNAME}@{host}")
        elif result['status'] == 'timeout':
            print("  • Check network connectivity")
            print("  • Verify host is reachable")
            print(f"  • Try ping: ping {host}")
            print(f"  • Check if SSH port {config.ETN_SSH_PORT} is open")
        else:
            print("  • Check if certificate file exists on the host")
            print("  • Verify openssl is installed")
            print("  • Check file permissions")
    
    print()
    print("=" * 70)
    
    return result


async def test_with_manual_command(host: str):
    """Show the manual SSH command for troubleshooting."""
    print()
    print("🛠️  Manual Test Command:")
    print("=" * 70)
    print()
    print(f"You can test manually with:")
    print()
    print(f"  ssh {config.ETN_SSH_USERNAME}@{host}")
    print()
    print("Then run:")
    print()
    print("  openssl x509 -enddate -noout -in /etc/vmware/nsx/host-cert.pem")
    print()
    print("=" * 70)


async def main():
    """Run the test."""
    # Default host
    default_host = "10.11.35.122"
    
    # Get host from command line or use default
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        host = default_host
    
    print()
    print("🧪 ETN Certificate Test - Single Host")
    print()
    
    # Validate config
    try:
        config.validate()
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print()
        print("Please check your .env file and ensure these variables are set:")
        print("  - NSX_USERNAME")
        print("  - NSX_PASSWORD")
        print("  - ETN_SSH_USERNAME")
        print("  - ETN_SSH_PASSWORD")
        return
    
    # Run test
    result = await test_single_etn(host)
    
    # Show manual command
    await test_with_manual_command(host)
    
    # Exit code
    if result['status'] == 'success':
        print("✅ Test completed successfully!")
        sys.exit(0)
    else:
        print("❌ Test failed. Check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

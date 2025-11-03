#!/usr/bin/env python3
"""
Тест аутентификации NSX-T Manager.
Проверяет правильность метода аутентификации через j_username/j_password.
"""
import requests
import sys
from pathlib import Path

# Disable SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load .env if available
try:
    from dotenv import load_dotenv
    import os
    
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print("✅ .env файл загружен\n")
    
    NSX_URL = os.getenv('NSX_MANAGER_URL', 'https://nsx01cast.t-cloud.kz')
    NSX_USERNAME = os.getenv('NSX_USERNAME', '')
    NSX_PASSWORD = os.getenv('NSX_PASSWORD', '')
except ImportError:
    NSX_URL = 'https://nsx01cast.t-cloud.kz'
    NSX_USERNAME = ''
    NSX_PASSWORD = ''


def test_nsx_auth(url, username, password):
    """Test NSX-T Manager authentication."""
    print("=" * 70)
    print("🔐 Тест аутентификации NSX-T Manager")
    print("=" * 70)
    print(f"\nURL: {url}")
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password) if password else '(не указан)'}\n")
    
    if not username or not password:
        print("❌ ОШИБКА: Username или Password не указаны!")
        print("\nДобавьте в .env:")
        print("  NSX_USERNAME=tadm.bisengaliyev@t-cloud.kz")
        print("  NSX_PASSWORD=ваш_пароль")
        return False
    
    session = requests.Session()
    session.verify = False
    
    # Step 1: Authenticate
    print("📝 Шаг 1: Аутентификация через /api/session/create")
    print("-" * 70)
    
    auth_url = f"{url.rstrip('/')}/api/session/create"
    print(f"POST {auth_url}")
    
    # Prepare form data
    auth_data = {
        'j_username': username,
        'j_password': password
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    print(f"Headers: {headers}")
    print(f"Body: j_username={username}, j_password=***")
    print()
    
    try:
        response = session.post(
            auth_url,
            data=auth_data,
            headers=headers,
            auth=requests.auth.HTTPBasicAuth(username, password),
            verify=False
        )
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers:")
        for key, value in response.headers.items():
            if key.upper() in ['X-XSRF-TOKEN', 'SET-COOKIE', 'CONTENT-TYPE']:
                print(f"  {key}: {value}")
        print()
        
        if response.status_code == 200:
            print("✅ Аутентификация успешна!")
            
            # Extract token
            xsrf_token = response.headers.get('X-XSRF-TOKEN')
            if xsrf_token:
                print(f"🔑 X-XSRF-TOKEN получен: {xsrf_token[:30]}...\n")
            else:
                print("⚠️  X-XSRF-TOKEN не найден в заголовках ответа\n")
                xsrf_token = None
        else:
            print(f"❌ Аутентификация не удалась!")
            print(f"Response Body: {response.text[:500]}\n")
            return False
        
    except Exception as e:
        print(f"❌ Ошибка при аутентификации: {str(e)}\n")
        return False
    
    # Step 2: Try to get transport nodes
    print("📝 Шаг 2: Получение списка Transport Nodes")
    print("-" * 70)
    
    api_url = f"{url.rstrip('/')}/api/v1/transport-nodes"
    print(f"GET {api_url}")
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    if xsrf_token:
        headers['X-XSRF-TOKEN'] = xsrf_token
    
    print(f"Headers: {headers}")
    print()
    
    try:
        response = session.get(api_url, headers=headers, verify=False)
        
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            total_nodes = len(data.get('results', []))
            print(f"✅ Успешно получен список Transport Nodes!")
            print(f"📊 Всего найдено: {total_nodes} nodes\n")
            
            # Show first few nodes
            if total_nodes > 0:
                print("Примеры (первые 3):")
                for node in data.get('results', [])[:3]:
                    node_deployment = node.get('node_deployment_info', {})
                    node_type = node_deployment.get('resource_type', 'Unknown')
                    display_name = node.get('display_name', 'N/A')
                    node_id = node.get('id', 'N/A')
                    
                    print(f"  • {display_name} (Type: {node_type}, ID: {node_id[:20]}...)")
                
                # Count edge nodes
                edge_count = sum(
                    1 for n in data.get('results', [])
                    if n.get('node_deployment_info', {}).get('resource_type') == 'EdgeNode'
                )
                print(f"\n🎯 Edge Transport Nodes: {edge_count}")
            
            return True
        else:
            print(f"❌ Не удалось получить Transport Nodes")
            print(f"Response Body: {response.text[:500]}\n")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при получении Transport Nodes: {str(e)}\n")
        return False


def main():
    """Main function."""
    print("\n🧪 NSX-T Manager Authentication Test\n")
    
    # Get credentials
    url = sys.argv[1] if len(sys.argv) > 1 else NSX_URL
    username = sys.argv[2] if len(sys.argv) > 2 else NSX_USERNAME
    password = sys.argv[3] if len(sys.argv) > 3 else NSX_PASSWORD
    
    if not url:
        print("❌ URL не указан!")
        print("\nИспользование:")
        print(f"  python {sys.argv[0]} <url> <username> <password>")
        print(f"  python {sys.argv[0]} https://nsx01cast.t-cloud.kz username password")
        sys.exit(1)
    
    success = test_nsx_auth(url, username, password)
    
    print("=" * 70)
    if success:
        print("✅ Все тесты пройдены успешно!")
        print("\nТеперь можно запускать основной сервис:")
        print("  docker-compose up -d")
    else:
        print("❌ Тесты завершились с ошибками")
        print("\n🔧 Проверьте:")
        print("  1. Правильность URL NSX Manager")
        print("  2. Username и Password")
        print("  3. Права доступа пользователя в NSX")
    print("=" * 70)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Тест прерван пользователем\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Неожиданная ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

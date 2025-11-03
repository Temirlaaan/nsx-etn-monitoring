#!/usr/bin/env python3
"""
Простой тест SSH подключения к ETN без зависимостей от основного проекта.
Требует только: pip install asyncssh python-dotenv
"""
import asyncio
import asyncssh
import sys
from datetime import datetime
from pathlib import Path

# Попытка загрузить .env
try:
    from dotenv import load_dotenv
    import os
    
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print("✅ .env файл загружен")
    else:
        print("⚠️  .env файл не найден, используйте параметры из командной строки")
    
    # Получить креды из .env
    SSH_USERNAME = os.getenv('ETN_SSH_USERNAME', 'admin')
    SSH_PASSWORD = os.getenv('ETN_SSH_PASSWORD', '')
    SSH_PORT = int(os.getenv('ETN_SSH_PORT', '22'))
    
except ImportError:
    print("⚠️  python-dotenv не установлен, используйте параметры командной строки")
    SSH_USERNAME = 'admin'
    SSH_PASSWORD = ''
    SSH_PORT = 22


async def test_etn_ssh(host, username=None, password=None, port=None):
    """Простой тест SSH подключения и чтения сертификата."""
    
    username = username or SSH_USERNAME
    password = password or SSH_PASSWORD
    port = port or SSH_PORT
    
    print("=" * 70)
    print(f"🔍 Тестирование ETN: {host}")
    print("=" * 70)
    print(f"\nПараметры подключения:")
    print(f"  Host: {host}")
    print(f"  Username: {username}")
    print(f"  Password: {'*' * len(password) if password else '(не указан)'}")
    print(f"  Port: {port}")
    print()
    
    if not password:
        print("❌ ОШИБКА: Пароль не указан!")
        print("\nИспользуйте:")
        print(f"  python {sys.argv[0]} {host} <username> <password>")
        print("\nИли создайте .env файл с ETN_SSH_PASSWORD")
        return False
    
    cert_path = '/etc/vmware/nsx/host-cert.pem'
    openssl_cmd = f'openssl x509 -enddate -noout -in {cert_path}'
    
    try:
        print("🔌 Подключение по SSH...")
        
        async with asyncssh.connect(
            host,
            username=username,
            password=password,
            port=port,
            known_hosts=None,
            connect_timeout=30
        ) as conn:
            
            print("✅ SSH подключение установлено!")
            print(f"\n📜 Выполнение команды: {openssl_cmd}")
            
            result = await conn.run(openssl_cmd, check=False, timeout=10)
            
            if result.exit_status != 0:
                print(f"\n❌ Ошибка выполнения команды:")
                print(f"Exit code: {result.exit_status}")
                print(f"STDERR: {result.stderr}")
                return False
            
            output = result.stdout.strip()
            print(f"\n✅ Команда выполнена успешно!")
            print(f"Вывод: {output}")
            
            # Парсинг даты
            if 'notAfter=' in output:
                date_str = output.split('notAfter=')[1].strip()
            else:
                date_str = output.strip()
            
            try:
                # Формат: Dec 31 23:59:59 2025 GMT
                expiry_date = datetime.strptime(date_str, '%b %d %H:%M:%S %Y %Z')
                days_remaining = (expiry_date - datetime.utcnow()).days
                
                print("\n" + "=" * 70)
                print("📊 РЕЗУЛЬТАТЫ")
                print("=" * 70)
                print(f"\n📅 Дата истечения: {expiry_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                print(f"⏰ Дней до истечения: {days_remaining}")
                
                # Статус
                if days_remaining <= 0:
                    print(f"\n🔴 КРИТИЧНО: Сертификат ИСТЁК {abs(days_remaining)} дней назад!")
                elif days_remaining <= 7:
                    print(f"\n🟠 ВНИМАНИЕ: Сертификат истекает через {days_remaining} дней!")
                elif days_remaining <= 30:
                    print(f"\n🟡 ПРЕДУПРЕЖДЕНИЕ: Сертификат истекает через {days_remaining} дней")
                else:
                    print(f"\n🟢 OK: Сертификат действителен ещё {days_remaining} дней")
                
                print("\n" + "=" * 70)
                return True
                
            except Exception as e:
                print(f"\n⚠️  Не удалось распарсить дату: {e}")
                print(f"Сырой вывод: {output}")
                return False
    
    except asyncssh.Error as e:
        print(f"\n❌ Ошибка SSH подключения: {str(e)}")
        print("\n🔧 Проверьте:")
        print("  1. Правильность IP адреса")
        print("  2. SSH креды (username/password)")
        print("  3. Доступность хоста (ping)")
        print("  4. SSH порт открыт")
        print(f"\n💡 Попробуйте вручную: ssh {username}@{host}")
        return False
    
    except asyncio.TimeoutError:
        print(f"\n❌ Таймаут подключения к {host}")
        print(f"\n💡 Проверьте доступность: ping {host}")
        return False
    
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def print_usage():
    """Показать справку по использованию."""
    print("\n📖 Использование:")
    print("\nВариант 1 - с .env файлом:")
    print(f"  python {sys.argv[0]} <host>")
    print(f"  python {sys.argv[0]} 10.11.35.122")
    print("\nВариант 2 - с параметрами:")
    print(f"  python {sys.argv[0]} <host> <username> <password> [port]")
    print(f"  python {sys.argv[0]} 10.11.35.122 admin mypassword 22")
    print()


async def main():
    """Главная функция."""
    print("\n🧪 Тест SSH подключения к ETN")
    print()
    
    # Парсинг аргументов
    if len(sys.argv) < 2:
        print("❌ Не указан IP адрес хоста!")
        print_usage()
        sys.exit(1)
    
    host = sys.argv[1]
    
    # Параметры подключения
    username = sys.argv[2] if len(sys.argv) > 2 else None
    password = sys.argv[3] if len(sys.argv) > 3 else None
    port = int(sys.argv[4]) if len(sys.argv) > 4 else None
    
    # Запуск теста
    success = await test_etn_ssh(host, username, password, port)
    
    if success:
        print("\n✅ Тест успешно завершен!\n")
        sys.exit(0)
    else:
        print("\n❌ Тест завершился с ошибками\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Тест прерван пользователем\n")
        sys.exit(1)

# ⚡ БЫСТРЫЙ ТЕСТ NSX API

## ✅ SSH тест уже прошел успешно!

```
ETN: 10.11.35.122
Сертификат истекает: 2028-02-02
Дней осталось: 821
Статус: 🟢 OK
```

---

## 🔐 Теперь тестируем NSX-T Manager API

### Метод 1: Быстрый тест (рекомендуется)

```bash
# Установить requests и python-dotenv
pip install requests python-dotenv

# Запустить тест NSX аутентификации
python test_nsx_auth.py
```

Скрипт проверит:
1. ✅ Аутентификацию через POST /api/session/create
2. ✅ Получение X-XSRF-TOKEN
3. ✅ Получение списка Transport Nodes
4. ✅ Подсчет Edge Transport Nodes

---

### Что исправлено в коде:

**Старый (неправильный) метод:**
```python
# Просто HTTPBasicAuth
response = session.post(auth_url, auth=HTTPBasicAuth(...))
```

**Новый (правильный) метод:**
```python
# Form data + Basic Auth
auth_data = {
    'j_username': 'tadm.bisengaliyev@t-cloud.kz',
    'j_password': 'password'
}
headers = {'Content-Type': 'application/x-www-form-urlencoded'}
response = session.post(auth_url, data=auth_data, headers=headers, auth=HTTPBasicAuth(...))

# Получить токен из ответа
xsrf_token = response.headers.get('X-XSRF-TOKEN')

# Использовать токен в последующих запросах
headers = {
    'Content-Type': 'application/json',
    'X-XSRF-TOKEN': xsrf_token
}
```

---

### Ваши креды в .env:

```env
NSX_MANAGER_URL=https://nsx01cast.t-cloud.kz
NSX_USERNAME=tadm.bisengaliyev@t-cloud.kz
NSX_PASSWORD=ваш_пароль
```

---

### Ожидаемый вывод при успехе:

```
🧪 NSX-T Manager Authentication Test

======================================================================
🔐 Тест аутентификации NSX-T Manager
======================================================================

URL: https://nsx01cast.t-cloud.kz
Username: tadm.bisengaliyev@t-cloud.kz
Password: *************

📝 Шаг 1: Аутентификация через /api/session/create
----------------------------------------------------------------------
POST https://nsx01cast.t-cloud.kz/api/session/create
Headers: {'Content-Type': 'application/x-www-form-urlencoded'}
Body: j_username=tadm.bisengaliyev@t-cloud.kz, j_password=***

Response Status: 200
Response Headers:
  X-XSRF-TOKEN: 9a8b7c6d5e4f3g2h1i...
  Content-Type: application/json

✅ Аутентификация успешна!
🔑 X-XSRF-TOKEN получен: 9a8b7c6d5e4f3g2h1i...

📝 Шаг 2: Получение списка Transport Nodes
----------------------------------------------------------------------
GET https://nsx01cast.t-cloud.kz/api/v1/transport-nodes
Headers: {'Content-Type': 'application/json', 'X-XSRF-TOKEN': '...'}

Response Status: 200
✅ Успешно получен список Transport Nodes!
📊 Всего найдено: 15 nodes

Примеры (первые 3):
  • edge1 (Type: EdgeNode, ID: e305ffb8-71db-11ec-...)
  • edge2 (Type: EdgeNode, ID: 55120a1a-51c6-4c20-...)
  • host1 (Type: HostNode, ID: 3f9dcf09-d6dd-45ca-...)

🎯 Edge Transport Nodes: 10

======================================================================
✅ Все тесты пройдены успешно!

Теперь можно запускать основной сервис:
  docker-compose up -d
======================================================================
```

---

### После успешного теста:

```bash
# Запустить полный тест (NSX + SSH + Telegram)
python test_connection.py

# Запустить основной сервис
docker-compose up -d

# Открыть веб-интерфейс
open http://localhost:8000
```

---

### Если тест не проходит:

**403 Authentication Failed:**
- Проверьте username и password в .env
- Убедитесь что пользователь имеет доступ к NSX API

**Connection timeout:**
- Проверьте доступность: `ping nsx01cast.t-cloud.kz`
- Проверьте firewall/proxy

**SSL ошибки:**
- Код уже отключает SSL verification
- Warnings подавлены

---

**Запустите тест прямо сейчас:** `python test_nsx_auth.py` 🚀

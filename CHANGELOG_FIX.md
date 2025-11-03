# 🔧 ИСПРАВЛЕНИЯ - NSX API Аутентификация

## ✅ Что было исправлено

### Проблема:
NSX-T Manager возвращал ошибку 403:
```
Authentication Failed: No AuthenticationProvider found for 
org.springframework.security.authentication.UsernamePasswordAuthenticationToken
```

### Причина:
Неправильный метод аутентификации. NSX-T требует специальный формат с `j_username` и `j_password` в теле запроса.

---

## 🔄 Изменения в коде

### Файл: `app/nsx_client.py`

**Было (неправильно):**
```python
def _get_session(self):
    # Просто Basic Auth
    response = self.session.post(
        auth_url,
        auth=HTTPBasicAuth(self.username, self.password),
        verify=False
    )
    # Пытались получить JSESSIONID из cookies
    self.cookies = {'JSESSIONID': response.cookies.get('JSESSIONID')}
```

**Стало (правильно):**
```python
def _get_session(self):
    # Form data с j_username и j_password
    auth_data = {
        'j_username': self.username,
        'j_password': self.password
    }
    
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
    
    # Получаем X-XSRF-TOKEN из заголовков ответа
    xsrf_token = response.headers.get('X-XSRF-TOKEN')
    self.cookies = {'X-XSRF-TOKEN': xsrf_token}
```

**И в методе _make_request:**
```python
def _make_request(self, method, endpoint, **kwargs):
    headers = kwargs.get('headers', {})
    
    # Добавляем Content-Type для API запросов
    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json'
    
    # Добавляем X-XSRF-TOKEN в заголовки
    if self.cookies.get('X-XSRF-TOKEN'):
        headers['X-XSRF-TOKEN'] = self.cookies['X-XSRF-TOKEN']
```

---

## 📝 Новые тестовые скрипты

### 1. `test_nsx_auth.py` - Тест NSX аутентификации
Специальный скрипт для проверки правильности аутентификации:
- POST на /api/session/create с правильным форматом
- Получение X-XSRF-TOKEN
- GET на /api/v1/transport-nodes с токеном
- Подробный вывод каждого шага

**Использование:**
```bash
pip install requests python-dotenv
python test_nsx_auth.py
```

### 2. Обновлен `test_connection.py`
Теперь использует исправленный NSXClient

---

## 🧪 Тестирование

### Шаг 1: Проверить SSH (✅ УЖЕ РАБОТАЕТ)
```bash
python test_simple.py 10.11.35.122
# Результат: Сертификат истекает 2028-02-02, 821 день
```

### Шаг 2: Проверить NSX API (ТЕСТИРУЕМ СЕЙЧАС)
```bash
python test_nsx_auth.py
# Должно показать успешную аутентификацию и список nodes
```

### Шаг 3: Полный тест
```bash
python test_connection.py
# Проверит NSX + SSH + Telegram
```

### Шаг 4: Запуск сервиса
```bash
docker-compose up -d
```

---

## 📋 Что нужно в .env

```env
# NSX-T Manager (ОБЯЗАТЕЛЬНО)
NSX_MANAGER_URL=https://nsx01cast.t-cloud.kz
NSX_USERNAME=tadm.bisengaliyev@t-cloud.kz
NSX_PASSWORD=ваш_пароль

# ETN SSH (ОБЯЗАТЕЛЬНО - УЖЕ РАБОТАЕТ)
ETN_SSH_USERNAME=root
ETN_SSH_PASSWORD=***************
ETN_SSH_PORT=22

# Telegram (ОПЦИОНАЛЬНО)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## 🎯 Ожидаемые результаты

После исправлений `test_nsx_auth.py` должен показать:
```
✅ Аутентификация успешна!
🔑 X-XSRF-TOKEN получен
✅ Успешно получен список Transport Nodes!
📊 Всего найдено: N nodes
🎯 Edge Transport Nodes: M
```

---

## 📚 Документация

- **TEST_NSX.md** - Подробная инструкция по тесту NSX
- **QUICK_TEST.md** - Быстрая инструкция
- **README.md** - Полная документация

---

## 🚀 Следующие шаги

1. ✅ SSH работает (10.11.35.122 - сертификат OK)
2. ⏳ Протестировать NSX: `python test_nsx_auth.py`
3. ⏳ Запустить сервис: `docker-compose up -d`
4. ⏳ Открыть веб: http://localhost:8000

---

**Дата исправлений:** 2024-11-03
**Версия:** 1.0.1

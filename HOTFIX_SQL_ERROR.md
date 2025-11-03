# 🔧 СРОЧНОЕ ИСПРАВЛЕНИЕ - SQL Query Error

## 🐛 Проблема
При открытии веб-интерфейса возникает ошибка:
```
sqlalchemy.exc.InvalidRequestError: Select statement returned no FROM clauses 
due to auto-correlation
```

## ✅ Решение
Исправлен SQL запрос в `/app/main.py` - упрощена логика получения последней проверки сертификатов.

---

## ⚡ БЫСТРОЕ ИСПРАВЛЕНИЕ

### Вариант 1: Перезапуск с новым кодом

```bash
# 1. Остановить контейнер
docker compose down

# 2. Скачать исправленный архив
# (используйте новый etn-cert-monitor.tar.gz)

# 3. Распаковать поверх существующего
tar -xzf etn-cert-monitor.tar.gz

# 4. Пересобрать и запустить
docker compose up -d --build
```

### Вариант 2: Ручное исправление (если не хотите перекачивать)

```bash
# 1. Остановить контейнер
docker compose down

# 2. Открыть файл
nano app/main.py

# 3. Найти функцию dashboard (строка ~95)
# И заменить весь блок запроса на упрощенную версию
# (см. ниже полный код функции)

# 4. Пересобрать и запустить
docker compose up -d --build
```

---

## 📝 Что было изменено

### Старый код (с ошибкой):
```python
# Сложный JOIN с subquery
query = (
    select(TransportNode, CertificateCheck)
    .outerjoin(
        CertificateCheck,
        and_(
            TransportNode.id == CertificateCheck.node_id,
            CertificateCheck.id == (
                select(func.max(CertificateCheck.id))
                .where(CertificateCheck.node_id == TransportNode.id)
                .scalar_subquery()
            )
        )
    )
    ...
)
```

### Новый код (исправленный):
```python
# Простой подход - два отдельных запроса
# 1. Получить все nodes
result = await db.execute(
    select(TransportNode)
    .where(TransportNode.is_active == True)
    .order_by(TransportNode.display_name)
)
nodes = result.scalars().all()

# 2. Для каждой node получить последнюю проверку
for node in nodes:
    check_result = await db.execute(
        select(CertificateCheck)
        .where(CertificateCheck.node_id == node.id)
        .order_by(CertificateCheck.checked_at.desc())
        .limit(1)
    )
    cert_check = check_result.scalar_one_or_none()
    ...
```

---

## 🚀 После исправления

```bash
# Проверить логи
docker compose logs -f

# Открыть браузер
http://localhost:8000
```

**Теперь должен открыться dashboard с 4 ETN!** ✅

---

## 📊 Что вы увидите

```
Dashboard:
- Всего ETN: 4
- Сертификаты OK: 0 (пока не проверены)
- Предупреждения: 0
- и т.д.

Таблица с 4 строками:
┌──────────────────────────┬─────────────┬─────────┬─────────────────┬───────────┬──────────────┐
│ Имя ETN                  │ IP Адрес    │ Режим   │ Дата истечения  │ Осталось  │ Статус       │
├──────────────────────────┼─────────────┼─────────┼─────────────────┼───────────┼──────────────┤
│ esg-ast-interconnect01   │ 10.11.35.7  │ DISABLED│ —               │ —         │ Не проверялся│
│ esg-ast-interconnect02   │ 10.11.35.8  │ DISABLED│ —               │ —         │ Не проверялся│
│ esg-ast-internet01       │ 10.11.35.2  │ DISABLED│ —               │ —         │ Не проверялся│
│ esg-ast-internet03       │ 10.11.35.11 │ DISABLED│ —               │ —         │ Не проверялся│
└──────────────────────────┴─────────────┴─────────┴─────────────────┴───────────┴──────────────┘
```

**Статус "Не проверялся"** - это нормально, сертификаты будут проверены:
- По расписанию (каждую неделю в понедельник в 03:00)
- ИЛИ можно запустить проверку вручную (см. ниже)

---

## 🔧 Ручной запуск проверки сертификатов

Чтобы не ждать расписания, можно запустить проверку прямо сейчас:

```bash
# Войти в контейнер
docker exec -it etn-cert-monitor bash

# Внутри контейнера запустить Python
python3 << 'EOF'
import asyncio
from app.scheduler import SchedulerService

async def run_check():
    service = SchedulerService()
    await service.check_certificates()

asyncio.run(run_check())
EOF

# Выйти
exit
```

Или через API (если добавим endpoint):
```bash
curl -X POST http://localhost:8000/api/trigger/cert-check
```

---

## 📝 Если нужен endpoint для ручного запуска

Можно добавить в `app/main.py`:

```python
@app.post("/api/trigger/cert-check")
async def trigger_cert_check():
    """Manually trigger certificate check."""
    if scheduler_service:
        asyncio.create_task(scheduler_service.check_certificates())
        return {"status": "triggered", "message": "Certificate check started"}
    return {"status": "error", "message": "Scheduler not running"}

@app.post("/api/trigger/nsx-sync")
async def trigger_nsx_sync():
    """Manually trigger NSX sync."""
    if scheduler_service:
        asyncio.create_task(scheduler_service.sync_nsx_nodes())
        return {"status": "triggered", "message": "NSX sync started"}
    return {"status": "error", "message": "Scheduler not running"}
```

Тогда можно запускать проверки через curl:
```bash
curl -X POST http://localhost:8000/api/trigger/cert-check
curl -X POST http://localhost:8000/api/trigger/nsx-sync
```

---

## ✅ Проверочный список

- ✅ Контейнер запущен: `docker ps | grep etn-cert-monitor`
- ✅ Логи без ошибок: `docker compose logs -f`
- ✅ Веб-интерфейс открывается: http://localhost:8000
- ✅ Показывает 4 ETN
- ✅ Telegram уведомления приходят

---

**Версия:** 1.1.1 (HOTFIX)  
**Дата:** 2024-11-03  
**Статус:** Исправлено ✅

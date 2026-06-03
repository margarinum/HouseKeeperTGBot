# House Bot Multi House

Рабочая версия бота для верификации жильцов по Google Sheets через Apps Script.

## Google Sheets

Первая строка листа `Лист1`:

`Номер дома | Номер подъезда | Этаж | Номер квартиры | Имя1 | ID1 | Имя2 | ID2 | ...`

## Установка

```bash
cd /opt/house_bot
pip3 install --break-system-packages -r requirements.txt
cp .env.example .env
nano .env
python3 main.py
```

Перед запуском вставьте код из `apps_script/Code.gs` в Google Apps Script, поменяйте `SECRET`, опубликуйте как Web App и вставьте URL в `.env`.

# اجرای NEXUS v0.5.6 در Windows

```bat
cd /d "D:\ai project test\signal-bot\Auto trade\NEXUS_v0.5.6_STANDARD_ADMIN_LICENSED_FINAL"
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
python run_api.py
```

در پنجره دوم CMD برای Bot:

```bat
cd /d "D:\ai project test\signal-bot\Auto trade\NEXUS_v0.5.6_STANDARD_ADMIN_LICENSED_FINAL"
.venv\Scripts\activate
python run.py
```

در MT5:
1. فایل `mt5\NEXUS_AutoTrade\NEXUS_AutoTrade.mq5` و پوشه Include را در مسیر MQL5 کپی کنید.
2. در MetaEditor Compile کنید؛ معیار انتشار EA، صفر Error است.
3. در Tools > Options > Expert Advisors، WebRequest را برای `http://127.0.0.1:8080` مجاز کنید.
4. برای Admin: `InpAdminMode=true` و Admin Token را وارد کنید؛ Account باید در Backend allow-list باشد.
5. برای Standard: License و Admin Token لازم نیست.

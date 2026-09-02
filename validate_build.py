from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', encoding='utf-8-sig')

required_env = [
    'BOT_TOKEN','ADMIN_IDS','PUBLIC_CHANNEL_ID','PUBLIC_CHANNEL_URL',
    'FREE_CHANNEL_URL','VIP_CHANNEL_ID','SUPPORT_USERNAME','PAYMENT_CARD','PAYMENT_OWNER'
]
missing=[k for k in required_env if not os.getenv(k,'').strip()]
print('NEXUS build validation')
print('----------------------')
print('Environment template:', 'OK' if (ROOT/'.env.example').is_file() else 'MISSING')
print('Runtime .env:', 'OK' if not missing else 'not configured in source package')
for rel in ['run.py','run_api.py','app/main.py','app/autotrade/api.py','mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5']:
    print(rel, 'OK' if (ROOT/rel).is_file() else 'MISSING')
ex5=ROOT/'assets/autotrade/NEXUS_AutoTrade.ex5'
print('Compiled EX5 installer:', 'PRESENT — verify it was compiled from the current MQ5' if ex5.is_file() else 'NOT PRESENT — source package requires MetaEditor compilation')
print('\nGuide videos:')
for name in ['NEXUS_Intro.mp4','NEXUS_Purchase_Guide.mp4','NEXUS_AutoTrade_MT5_Guide.mp4','NEXUS_AutoTrade_Crypto_Guide.mp4']:
    print(' assets/guides/'+name, 'OK' if (ROOT/'assets/guides'/name).is_file() else 'optional/not uploaded')
api_source=(ROOT/'mt5/NEXUS_AutoTrade/NEXUS_AutoTrade.mq5').read_text(encoding='utf-8', errors='ignore')
if 'http://127.0.0.1:8080' in api_source:
    print('\nWARNING: MT5 source still points to 127.0.0.1:8080.')
    print('This works only when MT5 and FastAPI run on the same machine.')
    print('Before customer deployment, compile EA with the public HTTPS NEXUS API URL.')

from __future__ import annotations
import hashlib,hmac,json,math,os,re,time,uuid
from datetime import datetime,timezone
from typing import Any
from urllib.parse import parse_qsl
from fastapi import APIRouter,Header,HTTPException,Query
from pydantic import BaseModel,Field,field_validator,model_validator
from . import db
from .autotrade.symbol_registry import infer_category,normalize_symbol
from .autotrade.trailing_profiles import TRAILING_PROFILES,profile_snapshot
router=APIRouter(prefix='/miniapp/api/admin',tags=['miniapp-admin-signal-center']);MAX_INIT_DATA_AGE=max(60,int(os.getenv('MINIAPP_AUTH_MAX_AGE_SECONDS','86400')));RR_MULTIPLIERS=(1.0,2.0,3.0)
def init_miniapp_admin_schema():
 with db.conn() as con:con.executescript("CREATE TABLE IF NOT EXISTS miniapp_admin_signal_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,request_id TEXT NOT NULL UNIQUE,admin_telegram_id INTEGER NOT NULL,signal_id INTEGER,status TEXT NOT NULL,error_message TEXT,payload_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);CREATE INDEX IF NOT EXISTS idx_miniapp_admin_signal_status ON miniapp_admin_signal_requests(status,updated_at);")
def _validate_init_data(raw):
 raw=str(raw or '').strip()
 if not raw:raise HTTPException(401,'missing Telegram initData')
 try:pairs=parse_qsl(raw,keep_blank_values=True,strict_parsing=True)
 except ValueError as e:raise HTTPException(401,'invalid Telegram initData') from e
 data=dict(pairs);received=str(data.pop('hash',''));from .config import settings;check='\n'.join(f'{k}={data[k]}' for k in sorted(data));secret=hmac.new(b'WebAppData',settings.bot_token.encode(),hashlib.sha256).digest();calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
 if not received or not hmac.compare_digest(calc,received):raise HTTPException(401,'Telegram initData signature is invalid')
 try:auth=int(data.get('auth_date','0'));user=json.loads(data.get('user','{}'));uid=int(user['id'])
 except Exception as e:raise HTTPException(401,'invalid Telegram user data') from e
 now=int(time.time())
 if auth<=0 or auth>now+60 or now-auth>MAX_INIT_DATA_AGE:raise HTTPException(401,'Telegram initData has expired')
 if uid not in settings.admin_ids:raise HTTPException(403,'NEXUS administrator access is required')
 return user
def _admin(v):return _validate_init_data(v or '')
def _digits_for(s,requested=None):
 if requested is not None:return max(0,min(int(requested),8))
 if s.endswith('JPY'):return 3
 if s.startswith(('XAU','XAG','BTC','ETH')) or s in {'US30','US100','SPX500'}:return 2
 return 5
def calculate_auto_targets(symbol,direction,entry,stop_loss,digits=None):
 s=normalize_symbol(symbol);side=str(direction).upper();e=float(entry);sl=float(stop_loss)
 if side not in {'BUY','SELL'}:raise ValueError('direction must be BUY or SELL')
 if not all(math.isfinite(x) and x>0 for x in (e,sl)):raise ValueError('entry and stop-loss must be positive finite numbers')
 if (side=='BUY' and sl>=e) or(side=='SELL' and sl<=e):raise ValueError('stop-loss is on the wrong side of entry')
 p=_digits_for(s,digits);e=round(e,p);sl=round(sl,p);r=round(abs(e-sl),p)
 if r<=0:raise ValueError('risk becomes zero after normalization')
 sign=1 if side=='BUY' else -1;t=[round(e+sign*r*m,p) for m in RR_MULTIPLIERS]
 return {'symbol':s,'direction':side,'digits':p,'entry':e,'stop_loss':sl,'risk':r,'targets':t,'target_multipliers':list(RR_MULTIPLIERS)}
def _admin_mt5_status():
 from .config import settings
 accounts=tuple(str(x) for x in settings.nexus_admin_mt5_accounts);row=None
 if accounts:
  with db.conn() as con:row=con.execute(f"SELECT account_number,ea_version,last_seen_at FROM mt5_heartbeats_v060 WHERE role='ADMIN' AND account_number IN ({','.join('?' for _ in accounts)}) ORDER BY last_seen_at DESC LIMIT 1",accounts).fetchone()
 age=None
 if row:
  try:age=(datetime.now(timezone.utc)-datetime.fromisoformat(str(row['last_seen_at']))).total_seconds()
  except ValueError:pass
 online=age is not None and age<=120;return {'online':online,'status':'ONLINE' if online else 'OFFLINE','account_number':str(row['account_number']) if row else(accounts[0] if accounts else None),'ea_version':str(row['ea_version'] or '') if row else None,'last_seen_at':str(row['last_seen_at']) if row else None,'age_seconds':age}
class CalculateRequest(BaseModel):
 symbol:str=Field(min_length=3,max_length=32);direction:str=Field(pattern='^(?:BUY|SELL)$');entry:float=Field(gt=0);stop_loss:float=Field(gt=0);digits:int|None=Field(default=None,ge=0,le=8)
class CreateSignalRequest(CalculateRequest):
 destination:str=Field(pattern='^(?:FREE|VIP|BOTH)$');request_id:str=Field(min_length=8,max_length=160);timeframe:str=Field(default='M5',pattern='^(?:M1|M3|M5|M15|M30|H1|H4|D1|W1)$');setup_mode:str=Field(default='MANUAL',pattern='^(?:MANUAL|AUTO)$');trailing_code:str;volume_mode:str=Field(default='RISK',pattern='^(?:RISK|FIXED)$');lot_size:float|None=Field(default=None,gt=0)
 @field_validator('request_id')
 @classmethod
 def safe_id(cls,v):
  v=v.strip()
  if not re.fullmatch(r'[A-Za-z0-9._:-]+',v):raise ValueError('invalid request_id')
  return v
 @field_validator('trailing_code')
 @classmethod
 def trail(cls,v):
  v=v.strip().upper()
  if v not in TRAILING_PROFILES:raise ValueError('unknown trailing profile')
  return v
 @model_validator(mode='after')
 def contract(self):
  if self.volume_mode=='FIXED' and self.lot_size is None:raise ValueError('lot_size is required for FIXED volume')
  if self.volume_mode=='RISK' and self.lot_size is not None:raise ValueError('lot_size must be empty for RISK volume')
  if self.setup_mode=='AUTO':raise ValueError('AUTO setup requires confirmed MT5 candle structure; market-data feed is not available yet')
  return self
def _sync_request(row):
 item=dict(row);sig=db.get_signal(int(item['signal_id'])) if item.get('signal_id') else None
 if sig:item['signal']=dict(sig);item['targets']=[float(x['price']) for x in db.get_signal_targets(int(sig['id']))]
 return item
@router.get('/bootstrap')
def bootstrap(x_telegram_init_data:str|None=Header(default=None,alias='X-Telegram-Init-Data')):
 u=_admin(x_telegram_init_data);return {'ok':True,'user':u,'mt5_admin':_admin_mt5_status(),'destinations':['FREE','VIP','BOTH'],'timeframes':['M1','M5','M15','M30','H1','H4'],'trailing_profiles':[{'code':k,'name':v['name']} for k,v in TRAILING_PROFILES.items()]}
@router.post('/signals/calculate')
def calculate(req:CalculateRequest,x_telegram_init_data:str|None=Header(default=None,alias='X-Telegram-Init-Data')):
 _admin(x_telegram_init_data)
 try:return calculate_auto_targets(req.symbol,req.direction,req.entry,req.stop_loss,req.digits)
 except ValueError as e:raise HTTPException(422,str(e)) from e
@router.post('/signals',status_code=201)
def create_signal(req:CreateSignalRequest,x_telegram_init_data:str|None=Header(default=None,alias='X-Telegram-Init-Data')):
 user=_admin(x_telegram_init_data);init_miniapp_admin_schema()
 with db.conn() as con:existing=con.execute('SELECT * FROM miniapp_admin_signal_requests WHERE request_id=?',(req.request_id,)).fetchone()
 if existing:return _sync_request(existing)
 try:
  c=calculate_auto_targets(req.symbol,req.direction,req.entry,req.stop_loss,req.digits);mt5=_admin_mt5_status();account=str(mt5.get('account_number') or '').strip()
  if not account:raise ValueError('NEXUS_ADMIN_MT5_ACCOUNTS is not configured')
  trail=profile_snapshot(req.trailing_code);token=f"MINIAPP:{int(user['id'])}:{req.request_id}";row=db.create_signal(market_type=infer_category(c['symbol']),symbol=c['symbol'],direction=c['direction'],entry_price=c['entry'],stop_loss=c['stop_loss'],targets=c['targets'],risk_percent=0,rr_ratio=3.0,destination=req.destination,chart_file_id=None,created_by=int(user['id']),timeframe=req.timeframe,order_type='MARKET',volume_mode=req.volume_mode,lot_size=req.lot_size,trailing_code=req.trailing_code,trailing_name=str(trail.get('name') or req.trailing_code),trailing_config=trail,publish_token=token)
  with db.conn() as con:con.execute("UPDATE signals SET signal_uuid=COALESCE(signal_uuid,?),issuer_type='WEB_ADMIN',issuer_account=?,issued_at=COALESCE(issued_at,?),status='DRAFT',publication_stage='WAITING_FOR_CHART' WHERE id=?",(str(uuid.uuid4()),account,db.now_iso(),int(row['id'])))
  job=db.create_chart_capture_job(int(row['id']),f"MINIAPP_ADMIN:{int(user['id'])}");status='READY' if mt5['online'] else 'WAITING_FOR_MT5';payload={**c,'setup_mode':req.setup_mode,'destination':req.destination,'timeframe':req.timeframe,'trailing_code':req.trailing_code,'trailing_config':trail,'volume_mode':req.volume_mode,'lot_size':req.lot_size,'mt5_account':account}
  with db.conn() as con:con.execute('INSERT INTO miniapp_admin_signal_requests(request_id,admin_telegram_id,signal_id,status,error_message,payload_json,created_at,updated_at) VALUES(?,?,?,?,NULL,?,?,?)',(req.request_id,int(user['id']),int(row['id']),status,json.dumps(payload,ensure_ascii=False),db.now_iso(),db.now_iso()));rr=con.execute('SELECT * FROM miniapp_admin_signal_requests WHERE request_id=?',(req.request_id,)).fetchone()
  db.add_signal_event(int(row['id']),'MINIAPP_SIGNAL_CREATED',actor_type='MINIAPP_ADMIN',actor_id=int(user['id']),request_id=req.request_id,correlation_id=str(row['code']),payload=payload);return _sync_request(rr)
 except ValueError as e:raise HTTPException(422,str(e)) from e
@router.get('/signals')
def list_signals(limit:int=Query(30,ge=1,le=100),x_telegram_init_data:str|None=Header(default=None,alias='X-Telegram-Init-Data')):
 u=_admin(x_telegram_init_data);init_miniapp_admin_schema()
 with db.conn() as con:rows=con.execute('SELECT * FROM miniapp_admin_signal_requests WHERE admin_telegram_id=? ORDER BY id DESC LIMIT ?',(int(u['id']),limit)).fetchall()
 return {'items':[_sync_request(x) for x in rows],'mt5_admin':_admin_mt5_status()}
@router.get('/positions')
def positions(x_telegram_init_data:str|None=Header(default=None,alias='X-Telegram-Init-Data')):
 _admin(x_telegram_init_data);mt5=_admin_mt5_status();a=str(mt5.get('account_number') or '');return {'mt5_admin':mt5,'positions':db.enrich_mt5_live_signals(db.mt5_live_positions(a,nexus_only=False),a) if a else [],'orders':db.enrich_mt5_live_signals(db.mt5_live_orders(a,nexus_only=False),a) if a else []}

#property strict
#property version   "1.10"
#property description "NEXUS authoritative MT5 candle and Bid/Ask feed for Mini App Live Charts"

input string InpApiBaseUrl="https://api.nexustrade.ir";
input string InpAdminToken="";
input string InpSymbols="XAUUSD,EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD";
input int    InpUpdateSeconds=5;
input int    InpBackfillBars=250;
input int    InpLiveBars=3;
input int    InpHttpTimeoutMs=10000;

bool g_backfill_sent=false;

string Trim(const string value)
  {
   string out=value;
   StringTrimLeft(out);
   StringTrimRight(out);
   return out;
  }

string Upper(const string value)
  {
   string out=value;
   StringToUpper(out);
   return out;
  }

string JsonEscape(const string value)
  {
   string out=value;
   StringReplace(out,"\\","\\\\");
   StringReplace(out,"\"","\\\"");
   StringReplace(out,"\r","\\r");
   StringReplace(out,"\n","\\n");
   return out;
  }

string ResolveBrokerSymbol(const string canonical)
  {
   string wanted=Upper(Trim(canonical));
   if(wanted=="") return "";
   if(SymbolSelect(wanted,true)) return wanted;

   int total=SymbolsTotal(false);
   for(int i=0;i<total;i++)
     {
      string name=SymbolName(i,false);
      string up=Upper(name);
      if(up==wanted)
        {
         SymbolSelect(name,true);
         return name;
        }
     }
   for(int i=0;i<total;i++)
     {
      string name=SymbolName(i,false);
      string up=Upper(name);
      if(StringFind(up,wanted)>=0)
        {
         SymbolSelect(name,true);
         return name;
        }
     }
   return "";
  }

string TimeframeCode(const ENUM_TIMEFRAMES tf)
  {
   if(tf==PERIOD_M1) return "M1";
   if(tf==PERIOD_M5) return "M5";
   if(tf==PERIOD_M15) return "M15";
   if(tf==PERIOD_H1) return "H1";
   if(tf==PERIOD_D1) return "D1";
   return "";
  }

string CandleJson(const MqlRates &bar,const int digits)
  {
   return "{\"time\":"+(string)((long)bar.time)+
          ",\"open\":"+DoubleToString(bar.open,digits)+
          ",\"high\":"+DoubleToString(bar.high,digits)+
          ",\"low\":"+DoubleToString(bar.low,digits)+
          ",\"close\":"+DoubleToString(bar.close,digits)+
          ",\"tick_volume\":"+(string)((long)bar.tick_volume)+"}";
  }

bool AppendQuote(string &payload,const string canonical,const string broker_symbol,bool &first_quote)
  {
   MqlTick tick;
   if(!SymbolInfoTick(broker_symbol,tick))
     {
      Print("NEXUS MarketFeed: SymbolInfoTick failed symbol=",broker_symbol," err=",GetLastError());
      return false;
     }
   if(tick.bid<=0 || tick.ask<=0 || tick.ask<tick.bid || tick.time_msc<=0)
     {
      Print("NEXUS MarketFeed: invalid Bid/Ask tick symbol=",broker_symbol);
      return false;
     }

   int digits=(int)SymbolInfoInteger(broker_symbol,SYMBOL_DIGITS);
   if(!first_quote) payload+=",";
   first_quote=false;
   payload+="{\"symbol\":\""+JsonEscape(canonical)+"\",";
   payload+="\"broker_symbol\":\""+JsonEscape(broker_symbol)+"\",";
   payload+="\"bid\":"+DoubleToString(tick.bid,digits)+",";
   payload+="\"ask\":"+DoubleToString(tick.ask,digits)+",";
   payload+="\"digits\":"+(string)digits+",";
   payload+="\"time_msc\":"+(string)((long)tick.time_msc)+"}";
   return true;
  }

bool AppendSeries(string &payload,const string canonical,const string broker_symbol,
                  const ENUM_TIMEFRAMES tf,const int bars_count,bool &first_series)
  {
   MqlRates rates[];
   ArraySetAsSeries(rates,true);
   int copied=CopyRates(broker_symbol,tf,0,bars_count,rates);
   if(copied<=0)
     {
      Print("NEXUS MarketFeed: CopyRates failed symbol=",broker_symbol," tf=",TimeframeCode(tf)," err=",GetLastError());
      return false;
     }

   int digits=(int)SymbolInfoInteger(broker_symbol,SYMBOL_DIGITS);
   if(!first_series) payload+=",";
   first_series=false;
   payload+="{\"symbol\":\""+JsonEscape(canonical)+"\",";
   payload+="\"broker_symbol\":\""+JsonEscape(broker_symbol)+"\",";
   payload+="\"timeframe\":\""+TimeframeCode(tf)+"\",";
   payload+="\"digits\":"+(string)digits+",\"candles\":[";

   bool first_bar=true;
   for(int i=copied-1;i>=0;i--)
     {
      if(rates[i].time<=0 || rates[i].open<=0 || rates[i].high<=0 || rates[i].low<=0 || rates[i].close<=0)
         continue;
      if(!first_bar) payload+=",";
      first_bar=false;
      payload+=CandleJson(rates[i],digits);
     }
   payload+="]}";
   return !first_bar;
  }

bool BuildPayload(string &payload,const int bars_count)
  {
   string symbols[];
   int count=StringSplit(InpSymbols,',',symbols);
   if(count<=0) return false;

   ENUM_TIMEFRAMES tfs[5]={PERIOD_M1,PERIOD_M5,PERIOD_M15,PERIOD_H1,PERIOD_D1};
   string account=(string)AccountInfoInteger(ACCOUNT_LOGIN);
   string broker=AccountInfoString(ACCOUNT_COMPANY);
   string server=AccountInfoString(ACCOUNT_SERVER);

   payload="{\"account_number\":\""+JsonEscape(account)+"\",";
   payload+="\"broker\":\""+JsonEscape(broker)+"\",";
   payload+="\"server\":\""+JsonEscape(server)+"\",";
   payload+="\"ea_version\":\"NEXUS-MARKET-FEED-1.1\",\"quotes\":[";

   bool first_quote=true;
   for(int s=0;s<count;s++)
     {
      string canonical=Upper(Trim(symbols[s]));
      if(canonical=="") continue;
      string broker_symbol=ResolveBrokerSymbol(canonical);
      if(broker_symbol=="")
        {
         Print("NEXUS MarketFeed: broker symbol not found for ",canonical);
         continue;
        }
      AppendQuote(payload,canonical,broker_symbol,first_quote);
     }

   payload+="],\"series\":[";
   bool first_series=true;
   for(int s=0;s<count;s++)
     {
      string canonical=Upper(Trim(symbols[s]));
      if(canonical=="") continue;
      string broker_symbol=ResolveBrokerSymbol(canonical);
      if(broker_symbol=="") continue;
      for(int t=0;t<ArraySize(tfs);t++)
         AppendSeries(payload,canonical,broker_symbol,tfs[t],bars_count,first_series);
     }
   payload+="]}";
   return !first_series;
  }

bool PostPayload(const string payload)
  {
   if(Trim(InpAdminToken)=="")
     {
      Print("NEXUS MarketFeed: Admin Token is required.");
      return false;
     }

   string url=InpApiBaseUrl+"/api/v1/autotrade/admin/market-candles";
   string headers="Content-Type: application/json\r\n";
   headers+="X-MT5-Account: "+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"\r\n";
   headers+="X-Admin-Mode: 1\r\n";
   headers+="X-NEXUS-Admin-Token: "+InpAdminToken+"\r\n";

   char data[];
   int data_len=StringToCharArray(payload,data,0,WHOLE_ARRAY,CP_UTF8);
   if(data_len>0) data_len--;
   if(data_len<0) data_len=0;
   ArrayResize(data,data_len);

   char result[];
   string response_headers="";
   ResetLastError();
   int http=WebRequest("POST",url,headers,InpHttpTimeoutMs,data,result,response_headers);
   if(http<0)
     {
      Print("NEXUS MarketFeed: WebRequest failed err=",GetLastError(),
            ". Add ",InpApiBaseUrl," to Tools > Options > Expert Advisors > Allow WebRequest.");
      return false;
     }
   if(http<200 || http>=300)
     {
      string response=CharArrayToString(result,0,-1,CP_UTF8);
      Print("NEXUS MarketFeed: backend rejected feed HTTP=",http," body=",response);
      return false;
     }
   return true;
  }

void PublishFeed()
  {
   int bars=g_backfill_sent ? MathMax(1,InpLiveBars) : MathMax(20,InpBackfillBars);
   string payload="";
   if(!BuildPayload(payload,bars))
     {
      Print("NEXUS MarketFeed: no valid market series available.");
      return;
     }
   if(PostPayload(payload))
     {
      if(!g_backfill_sent)
         Print("NEXUS MarketFeed: initial broker candle backfill uploaded.");
      g_backfill_sent=true;
     }
  }

int OnInit()
  {
   if(InpUpdateSeconds<1)
     {
      Print("NEXUS MarketFeed: InpUpdateSeconds must be >= 1");
      return INIT_PARAMETERS_INCORRECT;
     }
   EventSetTimer(InpUpdateSeconds);
   PublishFeed();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   PublishFeed();
  }

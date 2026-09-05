#property strict
#property version   "0.65"
#property description "NEXUS Web Signal Chart Screenshot Agent"

input string InpApiBaseUrl = "https://api.nexustrade.ir";
input string InpAdminToken = "";
input int    InpPollSeconds = 2;
input int    InpHttpTimeoutMs = 8000;
input int    InpChartLoadTimeoutMs = 5000;
input int    InpScreenshotWidth = 1280;
input int    InpScreenshotHeight = 720;

#define NEXUS_CHART_AGENT_VERSION "0.6.5-chart-agent"

string g_account = "";

string Upper(string value)
{
   StringToUpper(value);
   return value;
}

string Trim(string value)
{
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
}

string ApiUrl(string path)
{
   string base = Trim(InpApiBaseUrl);
   while(StringLen(base) > 0 && StringSubstr(base, StringLen(base)-1, 1) == "/")
      base = StringSubstr(base, 0, StringLen(base)-1);
   return base + path;
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\r", "\\r");
   StringReplace(value, "\n", "\\n");
   return value;
}

string Headers()
{
   return "Content-Type: application/json\r\n"
        + "X-MT5-Account: " + g_account + "\r\n"
        + "X-NEXUS-Admin-Token: " + InpAdminToken + "\r\n"
        + "X-EA-Version: " + NEXUS_CHART_AGENT_VERSION + "\r\n";
}

bool Http(const string method,const string path,const string body,int &status,string &response)
{
   char data[];
   char result[];
   string result_headers = "";
   ArrayResize(data,0);
   if(StringLen(body) > 0)
   {
      StringToCharArray(body,data,0,WHOLE_ARRAY,CP_UTF8);
      if(ArraySize(data) > 0)
         ArrayResize(data,ArraySize(data)-1);
   }
   ResetLastError();
   status = WebRequest(method,ApiUrl(path),Headers(),InpHttpTimeoutMs,data,result,result_headers);
   if(status == -1)
   {
      int err = GetLastError();
      Print("[NEXUS ChartAgent] WebRequest failed. error=",err," path=",path,
            ". Add API URL to MT5 Tools > Options > Expert Advisors > Allow WebRequest.");
      response = "";
      return false;
   }
   response = CharArrayToString(result,0,-1,CP_UTF8);
   return true;
}

int FindKeyValueStart(const string json,const string key)
{
   string needle = "\"" + key + "\":";
   int p = StringFind(json,needle);
   if(p < 0) return -1;
   p += StringLen(needle);
   while(p < StringLen(json))
   {
      ushort c = StringGetCharacter(json,p);
      if(c!=' ' && c!='\t' && c!='\r' && c!='\n') break;
      p++;
   }
   return p;
}

string JsonString(const string json,const string key,const string fallback="")
{
   int p = FindKeyValueStart(json,key);
   if(p < 0 || p >= StringLen(json) || StringSubstr(json,p,1) != "\"") return fallback;
   p++;
   string out = "";
   bool escape = false;
   for(int i=p;i<StringLen(json);i++)
   {
      string ch = StringSubstr(json,i,1);
      if(escape)
      {
         if(ch=="n") out += "\n";
         else if(ch=="r") out += "\r";
         else if(ch=="t") out += "\t";
         else out += ch;
         escape=false;
         continue;
      }
      if(ch=="\\") { escape=true; continue; }
      if(ch=="\"") break;
      out += ch;
   }
   return out;
}

long JsonLong(const string json,const string key,const long fallback=0)
{
   int p = FindKeyValueStart(json,key);
   if(p < 0) return fallback;
   string token="";
   for(int i=p;i<StringLen(json);i++)
   {
      string ch=StringSubstr(json,i,1);
      if(StringFind("-0123456789",ch)<0) break;
      token += ch;
   }
   return StringLen(token)>0 ? (long)StringToInteger(token) : fallback;
}

double JsonDouble(const string json,const string key,const double fallback=0.0)
{
   int p = FindKeyValueStart(json,key);
   if(p < 0) return fallback;
   string token="";
   for(int i=p;i<StringLen(json);i++)
   {
      string ch=StringSubstr(json,i,1);
      if(StringFind("-+0123456789.eE",ch)<0) break;
      token += ch;
   }
   return StringLen(token)>0 ? StringToDouble(token) : fallback;
}

int JsonDoubleArray(const string json,const string key,double &values[])
{
   ArrayResize(values,0);
   int p=FindKeyValueStart(json,key);
   if(p<0 || StringSubstr(json,p,1)!="[") return 0;
   int end=StringFind(json,"]",p+1);
   if(end<0) return 0;
   string part=StringSubstr(json,p+1,end-p-1);
   string pieces[];
   int count=StringSplit(part,',',pieces);
   for(int i=0;i<count;i++)
   {
      string t=Trim(pieces[i]);
      if(StringLen(t)==0) continue;
      int n=ArraySize(values);
      ArrayResize(values,n+1);
      values[n]=StringToDouble(t);
   }
   return ArraySize(values);
}

ENUM_TIMEFRAMES ParseTimeframe(string tf)
{
   tf=Upper(Trim(tf));
   if(tf=="M1") return PERIOD_M1;
   if(tf=="M3") return PERIOD_M3;
   if(tf=="M5") return PERIOD_M5;
   if(tf=="M15") return PERIOD_M15;
   if(tf=="M30") return PERIOD_M30;
   if(tf=="H1") return PERIOD_H1;
   if(tf=="H4") return PERIOD_H4;
   if(tf=="D1") return PERIOD_D1;
   if(tf=="W1") return PERIOD_W1;
   return PERIOD_M5;
}

string CanonicalSymbol(string symbol)
{
   symbol=Upper(symbol);
   string out="";
   for(int i=0;i<StringLen(symbol);i++)
   {
      ushort c=StringGetCharacter(symbol,i);
      if((c>='A' && c<='Z') || (c>='0' && c<='9'))
         out += StringSubstr(symbol,i,1);
   }
   return out;
}

string ResolveBrokerSymbol(const string requested)
{
   string canonical=CanonicalSymbol(requested);
   string current=CanonicalSymbol(_Symbol);
   if(current==canonical || StringFind(current,canonical)==0)
      return _Symbol;

   int total=SymbolsTotal(false);
   string best="";
   for(int i=0;i<total;i++)
   {
      string s=SymbolName(i,false);
      string n=CanonicalSymbol(s);
      if(n==canonical) return s;
      if(StringFind(n,canonical)==0 && StringLen(best)==0) best=s;
   }
   if(StringLen(best)>0) return best;

   total=SymbolsTotal(true);
   for(int i=0;i<total;i++)
   {
      string s=SymbolName(i,true);
      string n=CanonicalSymbol(s);
      if(n==canonical) return s;
      if(StringFind(n,canonical)==0 && StringLen(best)==0) best=s;
   }
   return best;
}

bool WaitChartReady(const string symbol,const ENUM_TIMEFRAMES tf)
{
   ulong start=GetTickCount64();
   MqlRates rates[];
   while(GetTickCount64()-start < (ulong)MathMax(1000,InpChartLoadTimeoutMs))
   {
      if(Bars(symbol,tf)>=50 && CopyRates(symbol,tf,0,50,rates)>10)
         return true;
      Sleep(100);
   }
   return false;
}

void DeleteShotObjects(const long chart_id,const string prefix)
{
   int total=ObjectsTotal(chart_id,-1,-1);
   for(int i=total-1;i>=0;i--)
   {
      string name=ObjectName(chart_id,i,-1,-1);
      if(StringFind(name,prefix)==0)
         ObjectDelete(chart_id,name);
   }
   ChartRedraw(chart_id);
}

bool DrawLevel(const long chart_id,const string name,const double price,const color clr,const ENUM_LINE_STYLE style,const string label)
{
   if(price<=0) return false;
   if(!ObjectCreate(chart_id,name,OBJ_HLINE,0,0,price)) return false;
   ObjectSetDouble(chart_id,name,OBJPROP_PRICE,price);
   ObjectSetInteger(chart_id,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(chart_id,name,OBJPROP_STYLE,style);
   ObjectSetInteger(chart_id,name,OBJPROP_WIDTH,1);
   ObjectSetInteger(chart_id,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(chart_id,name,OBJPROP_HIDDEN,true);
   ObjectSetString(chart_id,name,OBJPROP_TEXT,label);
   return true;
}

bool HexSha256(const uchar &raw[],string &hex)
{
   uchar key[];
   uchar hash[];
   ArrayResize(key,0);
   int n=CryptEncode(CRYPT_HASH_SHA256,raw,key,hash);
   if(n<=0) return false;
   hex="";
   for(int i=0;i<ArraySize(hash);i++)
      hex += StringFormat("%02x",(int)hash[i]);
   return StringLen(hex)==64;
}

bool Base64Encode(const uchar &raw[],string &out)
{
   uchar key[];
   uchar encoded[];
   ArrayResize(key,0);
   int n=CryptEncode(CRYPT_BASE64,raw,key,encoded);
   if(n<=0) return false;
   out=CharArrayToString(encoded,0,n,CP_UTF8);
   return StringLen(out)>0;
}

bool ReadFileBytes(const string filename,uchar &raw[])
{
   int handle=FileOpen(filename,FILE_READ|FILE_BIN);
   if(handle==INVALID_HANDLE) return false;
   long size=FileSize(handle);
   if(size<=0 || size>5000000)
   {
      FileClose(handle);
      return false;
   }
   ArrayResize(raw,(int)size);
   int read=FileReadArray(handle,raw,0,(int)size);
   FileClose(handle);
   return read==(int)size;
}

bool CaptureJob(const long job_id,const long signal_db_id,const string signal_code,const string requested_symbol,
                const string tf_text,const string direction,const double entry,const double sl,const double &targets[],
                string &broker_symbol,string &image_b64,string &sha256,string &error_text)
{
   broker_symbol=ResolveBrokerSymbol(requested_symbol);
   if(StringLen(broker_symbol)==0)
   {
      error_text="BROKER_SYMBOL_NOT_FOUND";
      return false;
   }
   if(!SymbolSelect(broker_symbol,true))
   {
      error_text="BROKER_SYMBOL_SELECT_FAILED";
      return false;
   }

   ENUM_TIMEFRAMES tf=ParseTimeframe(tf_text);
   long chart_id=ChartOpen(broker_symbol,tf);
   if(chart_id==0)
   {
      error_text="CHART_OPEN_FAILED";
      return false;
   }

   bool ok=false;
   string prefix="NXS.SHOT."+IntegerToString((int)job_id)+".";
   string filename="NEXUS_SHOT_"+IntegerToString((int)job_id)+"_"+signal_code+".png";

   do
   {
      if(!WaitChartReady(broker_symbol,tf))
      {
         error_text="CHART_DATA_TIMEOUT";
         break;
      }

      DeleteShotObjects(chart_id,prefix);
      color entry_color=clrDodgerBlue;
      color sl_color=clrTomato;
      color tp_color=clrLimeGreen;
      DrawLevel(chart_id,prefix+"ENTRY",entry,entry_color,STYLE_SOLID,"ENTRY");
      DrawLevel(chart_id,prefix+"SL",sl,sl_color,STYLE_SOLID,"SL");
      for(int i=0;i<ArraySize(targets);i++)
         DrawLevel(chart_id,prefix+"TP"+IntegerToString(i+1),targets[i],tp_color,STYLE_DASH,"TP"+IntegerToString(i+1));

      string title=prefix+"TITLE";
      if(ObjectCreate(chart_id,title,OBJ_LABEL,0,0,0))
      {
         ObjectSetInteger(chart_id,title,OBJPROP_CORNER,CORNER_LEFT_UPPER);
         ObjectSetInteger(chart_id,title,OBJPROP_XDISTANCE,18);
         ObjectSetInteger(chart_id,title,OBJPROP_YDISTANCE,18);
         ObjectSetInteger(chart_id,title,OBJPROP_COLOR,clrWhite);
         ObjectSetInteger(chart_id,title,OBJPROP_FONTSIZE,12);
         ObjectSetInteger(chart_id,title,OBJPROP_SELECTABLE,false);
         ObjectSetInteger(chart_id,title,OBJPROP_HIDDEN,true);
         ObjectSetString(chart_id,title,OBJPROP_TEXT,signal_code+"  "+Upper(requested_symbol)+"  "+Upper(direction)+"  "+Upper(tf_text));
      }
      ChartRedraw(chart_id);
      Sleep(250);

      FileDelete(filename);
      ResetLastError();
      if(!ChartScreenShot(chart_id,filename,InpScreenshotWidth,InpScreenshotHeight,ALIGN_RIGHT))
      {
         error_text="SCREENSHOT_FAILED_"+IntegerToString(GetLastError());
         break;
      }

      uchar raw[];
      if(!ReadFileBytes(filename,raw))
      {
         error_text="SCREENSHOT_READ_FAILED";
         break;
      }
      if(!HexSha256(raw,sha256))
      {
         error_text="SHA256_FAILED";
         break;
      }
      if(!Base64Encode(raw,image_b64))
      {
         error_text="BASE64_FAILED";
         break;
      }
      ok=true;
   }
   while(false);

   DeleteShotObjects(chart_id,prefix);
   ChartClose(chart_id);
   FileDelete(filename);
   return ok;
}

void FailJob(const long job_id,const string error_text)
{
   string body="{\"error_code\":\"CAPTURE_FAILED\",\"error_text\":\""+JsonEscape(error_text)+"\"}";
   int status=0; string response="";
   Http("POST","/api/v1/autotrade/admin/chart-capture/"+IntegerToString((int)job_id)+"/fail",body,status,response);
   Print("[NEXUS ChartAgent] Job ",job_id," failed: ",error_text," HTTP=",status);
}

void PollOnce()
{
   if(StringLen(Trim(InpAdminToken))<16) return;
   int status=0; string response="";
   if(!Http("GET","/api/v1/autotrade/admin/chart-capture/next","",status,response)) return;
   if(status!=200)
   {
      Print("[NEXUS ChartAgent] Poll HTTP=",status," body=",response);
      return;
   }
   if(StringFind(response,"\"job\":null")>=0) return;

   long job_id=JsonLong(response,"job_id",0);
   long signal_db_id=JsonLong(response,"signal_db_id",0);
   string signal_code=JsonString(response,"signal_code","");
   string symbol=JsonString(response,"symbol","");
   string timeframe=JsonString(response,"timeframe","M5");
   string direction=JsonString(response,"direction","");
   double entry=JsonDouble(response,"entry",0);
   double sl=JsonDouble(response,"sl",0);
   double targets[];
   JsonDoubleArray(response,"targets",targets);

   if(job_id<=0 || signal_db_id<=0 || StringLen(signal_code)==0 || StringLen(symbol)==0 || entry<=0 || sl<=0)
   {
      if(job_id>0) FailJob(job_id,"INVALID_JOB_PAYLOAD");
      return;
   }

   string broker_symbol="",image_b64="",sha256="",error_text="";
   if(!CaptureJob(job_id,signal_db_id,signal_code,symbol,timeframe,direction,entry,sl,targets,
                  broker_symbol,image_b64,sha256,error_text))
   {
      FailJob(job_id,error_text);
      return;
   }

   string body="{"
      "\"signal_db_id\":"+IntegerToString((int)signal_db_id)+","+
      "\"signal_code\":\""+JsonEscape(signal_code)+"\","+
      "\"broker_symbol\":\""+JsonEscape(broker_symbol)+"\","+
      "\"timeframe\":\""+JsonEscape(timeframe)+"\","+
      "\"image_base64\":\""+image_b64+"\","+
      "\"image_sha256\":\""+sha256+"\"}";
   status=0; response="";
   if(!Http("POST","/api/v1/autotrade/admin/chart-capture/"+IntegerToString((int)job_id)+"/result",body,status,response))
   {
      Print("[NEXUS ChartAgent] Upload transport failed for job ",job_id);
      return;
   }
   if(status<200 || status>=300)
   {
      Print("[NEXUS ChartAgent] Upload rejected. job=",job_id," HTTP=",status," body=",response);
      return;
   }
   Print("[NEXUS ChartAgent] Screenshot uploaded. job=",job_id," signal=",signal_code," symbol=",broker_symbol);
}

int OnInit()
{
   g_account=IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN));
   if(StringLen(Trim(InpAdminToken))<16)
   {
      Print("[NEXUS ChartAgent] InpAdminToken is not configured.");
      return INIT_PARAMETERS_INCORRECT;
   }
   int seconds=MathMax(1,InpPollSeconds);
   EventSetTimer(seconds);
   Print("[NEXUS ChartAgent] Started account=",g_account," api=",InpApiBaseUrl,
         " interval=",seconds,"s. This EA is screenshot-only and never trades.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PollOnce();
}

void OnTick()
{
   // Intentionally empty. Screenshot work is isolated from NEXUS_AutoTrade.ex5.
}

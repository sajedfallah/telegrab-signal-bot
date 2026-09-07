#property strict
#property version   "1.000"
#property description "NEXUS Web Signal Chart Screenshot Agent"

input string InpApiBaseUrl = "https://api.nexustrade.ir";
input string InpAdminToken = "";
input int    InpPollSeconds = 2;
input int    InpHttpTimeoutMs = 8000;
input int    InpChartLoadTimeoutMs = 5000;
input int    InpScreenshotWidth = 1280;
input int    InpScreenshotHeight = 720;
input string InpChartTemplate = "NEXUS_Screenshot.tpl";
input int    InpTemplateLoadDelayMs = 500;
input double InpChartShiftPercent = 27.0;
input int    InpTradeLineWidth = 2;
input int    InpExitLineWidth = 1;
input int    InpLabelFontSize = 8;
input int    InpLabelNameWidth = 46;
input int    InpLabelPriceWidth = 64;
input int    InpLabelHeight = 18;
input int    InpLabelRightMargin = 72;

#define NEXUS_CHART_AGENT_VERSION "0.6.5-chart-agent"
#define NEXUS_CHART_VISUAL_PROFILE "approved-inline-level-v2"

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

bool WaitChartInstanceReady(const long chart_id,const string symbol,const ENUM_TIMEFRAMES tf)
{
   ulong start=GetTickCount64();
   ulong timeout=(ulong)MathMax(3000,InpChartLoadTimeoutMs);

   while(GetTickCount64()-start < timeout)
   {
      long width=0;
      if(ChartSymbol(chart_id)==symbol &&
         ChartPeriod(chart_id)==tf &&
         ChartGetInteger(chart_id,CHART_WIDTH_IN_PIXELS,0,width) &&
         width>0)
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

datetime LastCandleRightEdge(const string symbol,const ENUM_TIMEFRAMES tf)
{
   datetime open_time=iTime(symbol,tf,0);
   int seconds=PeriodSeconds(tf);
   if(seconds<=0) seconds=60;
   if(open_time<=0) open_time=TimeCurrent();
   return open_time+(datetime)seconds;
}

bool DrawTradeRay(const long chart_id,const string name,const datetime start_time,
                  const ENUM_TIMEFRAMES tf,const double price,const color clr,
                  const ENUM_LINE_STYLE style,const int width)
{
   if(price<=0 || start_time<=0) return false;

   int seconds=PeriodSeconds(tf);
   if(seconds<=0) seconds=60;
   datetime second_time=start_time+(datetime)seconds;

   if(!ObjectCreate(chart_id,name,OBJ_TREND,0,start_time,price,second_time,price))
      return false;

   ObjectSetInteger(chart_id,name,OBJPROP_COLOR,clr);
   ObjectSetInteger(chart_id,name,OBJPROP_STYLE,style);
   ObjectSetInteger(chart_id,name,OBJPROP_WIDTH,MathMax(1,width));
   ObjectSetInteger(chart_id,name,OBJPROP_RAY_LEFT,false);
   ObjectSetInteger(chart_id,name,OBJPROP_RAY_RIGHT,true);
   ObjectSetInteger(chart_id,name,OBJPROP_BACK,false);
   ObjectSetInteger(chart_id,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(chart_id,name,OBJPROP_SELECTED,false);
   ObjectSetInteger(chart_id,name,OBJPROP_HIDDEN,true);
   return true;
}

bool DrawCompactTag(const long chart_id,const string prefix,const string key,
                    const datetime reference_time,const double price,
                    const color accent_color,const string caption,
                    const int digits)
{
   int x=0,y=0;
   if(!ChartTimePriceToXY(chart_id,0,reference_time,price,x,y))
      return false;

   long chart_height=0;
   if(!ChartGetInteger(chart_id,CHART_HEIGHT_IN_PIXELS,0,chart_height) || chart_height<=0)
      return false;

   int height=MathMax(14,InpLabelHeight);
   int name_width=MathMax(36,InpLabelNameWidth);
   int price_width=MathMax(54,InpLabelPriceWidth);
   int center_y=y;
   int top=center_y-height/2;
   if(top<1 || top+height>(int)chart_height-1)
      return false;

   int margin=MathMax(4,InpLabelRightMargin);
   string name_box=prefix+key+".NAME.BOX";
   string price_box=prefix+key+".PRICE.BOX";
   string name_text=prefix+key+".NAME.TEXT";
   string price_text=prefix+key+".PRICE.TEXT";

   if(!ObjectCreate(chart_id,price_box,OBJ_RECTANGLE_LABEL,0,0,0))
      return false;
   ObjectSetInteger(chart_id,price_box,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
   ObjectSetInteger(chart_id,price_box,OBJPROP_XDISTANCE,margin);
   ObjectSetInteger(chart_id,price_box,OBJPROP_YDISTANCE,top);
   ObjectSetInteger(chart_id,price_box,OBJPROP_XSIZE,price_width);
   ObjectSetInteger(chart_id,price_box,OBJPROP_YSIZE,height);
   ObjectSetInteger(chart_id,price_box,OBJPROP_BGCOLOR,accent_color);
   ObjectSetInteger(chart_id,price_box,OBJPROP_COLOR,accent_color);
   ObjectSetInteger(chart_id,price_box,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(chart_id,price_box,OBJPROP_WIDTH,1);
   ObjectSetInteger(chart_id,price_box,OBJPROP_BACK,false);
   ObjectSetInteger(chart_id,price_box,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(chart_id,price_box,OBJPROP_SELECTED,false);
   ObjectSetInteger(chart_id,price_box,OBJPROP_HIDDEN,true);

   color tag_background=C'15,21,31';
   if(!ObjectCreate(chart_id,name_box,OBJ_RECTANGLE_LABEL,0,0,0))
      return false;
   ObjectSetInteger(chart_id,name_box,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
   ObjectSetInteger(chart_id,name_box,OBJPROP_XDISTANCE,margin+price_width);
   ObjectSetInteger(chart_id,name_box,OBJPROP_YDISTANCE,top);
   ObjectSetInteger(chart_id,name_box,OBJPROP_XSIZE,name_width);
   ObjectSetInteger(chart_id,name_box,OBJPROP_YSIZE,height);
   ObjectSetInteger(chart_id,name_box,OBJPROP_BGCOLOR,tag_background);
   ObjectSetInteger(chart_id,name_box,OBJPROP_COLOR,tag_background);
   ObjectSetInteger(chart_id,name_box,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(chart_id,name_box,OBJPROP_WIDTH,1);
   ObjectSetInteger(chart_id,name_box,OBJPROP_BACK,false);
   ObjectSetInteger(chart_id,name_box,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(chart_id,name_box,OBJPROP_SELECTED,false);
   ObjectSetInteger(chart_id,name_box,OBJPROP_HIDDEN,true);

   if(!ObjectCreate(chart_id,name_text,OBJ_LABEL,0,0,0))
      return false;
   ObjectSetInteger(chart_id,name_text,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
   ObjectSetInteger(chart_id,name_text,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(chart_id,name_text,OBJPROP_XDISTANCE,margin+price_width+name_width/2);
   ObjectSetInteger(chart_id,name_text,OBJPROP_YDISTANCE,center_y);
   ObjectSetInteger(chart_id,name_text,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(chart_id,name_text,OBJPROP_FONTSIZE,MathMax(7,InpLabelFontSize));
   ObjectSetInteger(chart_id,name_text,OBJPROP_BACK,false);
   ObjectSetInteger(chart_id,name_text,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(chart_id,name_text,OBJPROP_SELECTED,false);
   ObjectSetInteger(chart_id,name_text,OBJPROP_HIDDEN,true);
   ObjectSetString(chart_id,name_text,OBJPROP_FONT,"Arial");
   ObjectSetString(chart_id,name_text,OBJPROP_TEXT,caption);

   if(!ObjectCreate(chart_id,price_text,OBJ_LABEL,0,0,0))
      return false;
   ObjectSetInteger(chart_id,price_text,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
   ObjectSetInteger(chart_id,price_text,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(chart_id,price_text,OBJPROP_XDISTANCE,margin+price_width/2);
   ObjectSetInteger(chart_id,price_text,OBJPROP_YDISTANCE,center_y);
   ObjectSetInteger(chart_id,price_text,OBJPROP_COLOR,C'9,14,22');
   ObjectSetInteger(chart_id,price_text,OBJPROP_FONTSIZE,MathMax(7,InpLabelFontSize));
   ObjectSetInteger(chart_id,price_text,OBJPROP_BACK,false);
   ObjectSetInteger(chart_id,price_text,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(chart_id,price_text,OBJPROP_SELECTED,false);
   ObjectSetInteger(chart_id,price_text,OBJPROP_HIDDEN,true);
   ObjectSetString(chart_id,price_text,OBJPROP_FONT,"Arial");
   ObjectSetString(chart_id,price_text,OBJPROP_TEXT,
                   DoubleToString(price,MathMax(0,digits)));
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

   ulong file_size=FileSize(handle);
   if(file_size==0 || file_size>5000000)
   {
      FileClose(handle);
      return false;
   }

   int byte_count=(int)file_size;
   ArrayResize(raw,byte_count);

   uint bytes_read=FileReadArray(handle,raw,0,byte_count);
   FileClose(handle);

   return bytes_read==(uint)byte_count;
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

   if(!WaitChartInstanceReady(chart_id,broker_symbol,tf))
   {
      error_text="CHART_INSTANCE_NOT_READY";
      ChartClose(chart_id);
      return false;
   }

   if(StringLen(Trim(InpChartTemplate))>0)
   {
      ResetLastError();

      if(!ChartApplyTemplate(chart_id,InpChartTemplate))
      {
         int template_error=GetLastError();
         error_text="CHART_TEMPLATE_APPLY_FAILED_"+IntegerToString(template_error);
         ChartClose(chart_id);
         return false;
      }

      long template_background=0;
      long template_grid=0;

      ResetLastError();
      if(!ChartGetInteger(chart_id,CHART_COLOR_BACKGROUND,0,template_background))
      {
         int sync_error=GetLastError();
         error_text="CHART_TEMPLATE_SYNC_FAILED_"+IntegerToString(sync_error);
         ChartClose(chart_id);
         return false;
      }

      if(!ChartGetInteger(chart_id,CHART_SHOW_GRID,0,template_grid))
      {
         int grid_error=GetLastError();
         error_text="CHART_TEMPLATE_GRID_READ_FAILED_"+IntegerToString(grid_error);
         ChartClose(chart_id);
         return false;
      }

      ChartRedraw(chart_id);
      Sleep(MathMax(100,InpTemplateLoadDelayMs));

      Print("[NEXUS ChartAgent] Template synchronized. chart=",chart_id,
            " template=",InpChartTemplate,
            " background=",template_background,
            " grid=",template_grid);
   }

   if(!WaitChartReady(broker_symbol,tf))
   {
      error_text="CHART_DATA_TIMEOUT";
      ChartClose(chart_id);
      return false;
   }

   ChartSetInteger(chart_id,CHART_AUTOSCROLL,false);
   ChartSetInteger(chart_id,CHART_SHIFT,true);
   double shift=MathMax(10.0,MathMin(45.0,InpChartShiftPercent));
   ChartSetDouble(chart_id,CHART_SHIFT_SIZE,shift);
   ChartNavigate(chart_id,CHART_END,0);
   ChartRedraw(chart_id);
   Sleep(100);

   bool ok=false;
   string prefix="NXS.SHOT."+IntegerToString((int)job_id)+".";
   string filename="NEXUS_SHOT_"+IntegerToString((int)job_id)+"_"+signal_code+".png";

   do
   {
      DeleteShotObjects(chart_id,prefix);

      datetime level_start=LastCandleRightEdge(broker_symbol,tf);
      datetime label_reference=level_start;
      if(level_start<=0 || label_reference<=0)
      {
         error_text="LAST_CANDLE_TIME_UNAVAILABLE";
         break;
      }

      color entry_color=C'0,174,255';
      color sl_color=C'255,68,84';
      color tp_color=C'44,214,85';

      if(!DrawTradeRay(chart_id,prefix+"ENTRY.RAY",level_start,tf,entry,
                       entry_color,STYLE_SOLID,InpTradeLineWidth))
      {
         error_text="ENTRY_RAY_DRAW_FAILED";
         break;
      }

      if(!DrawTradeRay(chart_id,prefix+"SL.RAY",level_start,tf,sl,
                       sl_color,STYLE_SOLID,InpTradeLineWidth))
      {
         error_text="SL_RAY_DRAW_FAILED";
         break;
      }

      for(int i=0;i<ArraySize(targets);i++)
      {
         if(!DrawTradeRay(chart_id,prefix+"TP"+IntegerToString(i+1)+".RAY",
                          level_start,tf,targets[i],tp_color,STYLE_DASH,InpExitLineWidth))
         {
            error_text="TP_RAY_DRAW_FAILED_"+IntegerToString(i+1);
            break;
         }
      }
      if(StringLen(error_text)>0) break;

      ChartRedraw(chart_id);
      Sleep(100);

      int digits=(int)SymbolInfoInteger(broker_symbol,SYMBOL_DIGITS);
      if(digits<0) digits=2;

      if(!DrawCompactTag(chart_id,prefix,"ENTRY.TAG",label_reference,entry,
                         entry_color,"Entry",digits))
      {
         error_text="ENTRY_TAG_DRAW_FAILED";
         break;
      }

      if(!DrawCompactTag(chart_id,prefix,"SL.TAG",label_reference,sl,
                         sl_color,"SL",digits))
      {
         error_text="SL_TAG_DRAW_FAILED";
         break;
      }

      for(int i=0;i<ArraySize(targets);i++)
      {
         string caption="TP"+IntegerToString(i+1);
         if(!DrawCompactTag(chart_id,prefix,
                            "TP"+IntegerToString(i+1)+".TAG",
                            label_reference,targets[i],tp_color,caption,digits))
         {
            error_text="TP_TAG_DRAW_FAILED_"+IntegerToString(i+1);
            break;
         }
      }
      if(StringLen(error_text)>0) break;

      string title=prefix+"TITLE";
      if(ObjectCreate(chart_id,title,OBJ_LABEL,0,0,0))
      {
         ObjectSetInteger(chart_id,title,OBJPROP_CORNER,CORNER_LEFT_UPPER);
         ObjectSetInteger(chart_id,title,OBJPROP_XDISTANCE,16);
         ObjectSetInteger(chart_id,title,OBJPROP_YDISTANCE,16);
         ObjectSetInteger(chart_id,title,OBJPROP_COLOR,clrWhite);
         ObjectSetInteger(chart_id,title,OBJPROP_FONTSIZE,10);
         ObjectSetInteger(chart_id,title,OBJPROP_SELECTABLE,false);
         ObjectSetInteger(chart_id,title,OBJPROP_SELECTED,false);
         ObjectSetInteger(chart_id,title,OBJPROP_HIDDEN,true);
         ObjectSetString(chart_id,title,OBJPROP_FONT,"Arial");
         ObjectSetString(chart_id,title,OBJPROP_TEXT,
                         signal_code+"  "+Upper(requested_symbol)+"  "+
                         Upper(direction)+"  "+Upper(tf_text));
      }

      ChartRedraw(chart_id);
      Sleep(250);

      Print("[NEXUS ChartAgent] Visual profile=",NEXUS_CHART_VISUAL_PROFILE,
            " start=",TimeToString(level_start,TIME_DATE|TIME_MINUTES),
            " label_font=",InpLabelFontSize,
            " shift=",DoubleToString(shift,1));

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
         " interval=",seconds,"s visual=",NEXUS_CHART_VISUAL_PROFILE,
         ". This EA is screenshot-only and never trades.");
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

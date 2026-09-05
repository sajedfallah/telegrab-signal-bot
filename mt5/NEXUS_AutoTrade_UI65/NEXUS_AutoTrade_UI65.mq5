// NEXUS AutoTrade UI65
//
// This file is a presentation shell over the exact hardened production EA.
// The production trading/execution source stays untouched in NEXUS_AutoTrade.mq5.
// Event handlers are renamed while the core is included, then thin UI-aware
// entry points delegate back to the hardened handlers.

#define OnInit                 NEXUSCore_OnInit
#define OnDeinit               NEXUSCore_OnDeinit
#define OnTimer                NEXUSCore_OnTimer
#define OnTick                 NEXUSCore_OnTick
#define OnTradeTransaction     NEXUSCore_OnTradeTransaction
#define OnChartEvent           NEXUSCore_OnChartEvent
#include "NEXUS_AutoTrade.mq5"
#undef OnInit
#undef OnDeinit
#undef OnTimer
#undef OnTick
#undef OnTradeTransaction
#undef OnChartEvent

bool   g_ui65_reviewing=false;
string g_ui65_confirm_command="";
string g_ui65_setup_status="";

string UI65Name(const string name)
  {
   return NXS_UI_PREFIX+name;
  }

void UI65Delete(const string name)
  {
   ObjectDelete(0,UI65Name(name));
  }

string UI65Text(const string name,const string fallback="")
  {
   string n=UI65Name(name);
   if(ObjectFind(0,n)<0) return fallback;
   string value=ObjectGetString(0,n,OBJPROP_TEXT);
   return value=="" ? fallback : value;
  }

void UI65Label(const string name,const string text,const int x,const int y,const int size=10,const color fg=C'220,226,232')
  {
   string n=UI65Name(name);
   if(ObjectFind(0,n)<0) ObjectCreate(0,n,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,size);
   ObjectSetInteger(0,n,OBJPROP_COLOR,fg);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTED,false);
   ObjectSetInteger(0,n,OBJPROP_ZORDER,120);
   ObjectSetString(0,n,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,n,OBJPROP_TEXT,text);
  }

void UI65Edit(const string name,const string value,const int x,const int y,const int w,const int h)
  {
   string n=UI65Name(name);
   if(ObjectFind(0,n)<0)
     {
      if(!ObjectCreate(0,n,OBJ_EDIT,0,0,0)) return;
     }
   ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,n,OBJPROP_XSIZE,w);
   ObjectSetInteger(0,n,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,n,OBJPROP_BGCOLOR,C'31,38,46');
   ObjectSetInteger(0,n,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,n,OBJPROP_BORDER_COLOR,C'72,84,96');
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,10);
   ObjectSetInteger(0,n,OBJPROP_READONLY,false);
   ObjectSetInteger(0,n,OBJPROP_ALIGN,ALIGN_LEFT);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTED,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
   ObjectSetInteger(0,n,OBJPROP_ZORDER,130);
   ObjectSetString(0,n,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,n,OBJPROP_TEXT,value);
  }

void UI65HiddenEdit(const string name,const string value)
  {
   UI65Edit(name,value,5000,5000,1,1);
   ObjectSetInteger(0,UI65Name(name),OBJPROP_TIMEFRAMES,0);
  }

void UI65Button(const string name,const string text,const int x,const int y,const int w,const int h,const color bg=C'48,57,66')
  {
   string n=UI65Name(name);
   if(ObjectFind(0,n)<0) ObjectCreate(0,n,OBJ_BUTTON,0,0,0);
   ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,n,OBJPROP_XSIZE,w);
   ObjectSetInteger(0,n,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,n,OBJPROP_BGCOLOR,bg);
   ObjectSetInteger(0,n,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,n,OBJPROP_BORDER_COLOR,C'72,84,96');
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,9);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTED,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,false);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
   ObjectSetInteger(0,n,OBJPROP_ZORDER,140);
   ObjectSetString(0,n,OBJPROP_FONT,"Segoe UI");
   ObjectSetString(0,n,OBJPROP_TEXT,text);
  }

void UI65DeleteAll()
  {
   int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
     {
      string n=ObjectName(0,i,0,-1);
      if(StringFind(n,NXS_UI_PREFIX)==0) ObjectDelete(0,n);
     }
   ChartRedraw();
  }

void UI65DeleteSignalPanel()
  {
   string names[]={
      "sig_title","sig_legacy","sig_sub","sig_symbol_lbl","sig_symbol","sig_entry_lbl","sig_entry",
      "sig_sl_lbl","sig_sl","sig_tp1_lbl","sig_tp1","sig_tp2_lbl","sig_tp2","sig_tp3_lbl","sig_tp3",
      "sig_tp4_lbl","sig_tp4","sig_tp5_lbl","sig_tp5","sig_risk_lbl","sig_risk","sig_buy","sig_sell",
      "sig_market","sig_limit","sig_size_lbl","sig_size_risk","sig_size_fixed","sig_lot","sig_lot_hint",
      "sig_trail_lbl","sig_trail_01","sig_trail_02","sig_trail_03","sig_trail_04","sig_trail_05","sig_trail_06","sig_trail_07",
      "sig_dest_lbl","sig_dest_free","sig_dest_vip","sig_dest_both","sig_dest_state","sig_review","sig_review_back",
      "sig_issue","sig_review_summary","sig_review_summary2","sig_min"
   };
   for(int i=0;i<ArraySize(names);i++) UI65Delete(names[i]);
  }

void UI65DeleteTradePanel()
  {
   string names[]={
      "trade_title","trade_meta","trade_state","trade_hint","trade_confirm_text","trade_confirm","trade_abort",
      "sig_manage_title","sig_manage_id_lbl","sig_manage_id","sig_manage_value_lbl","sig_manage_value",
      "sig_be","sig_close","sig_cancel","sig_setsl","sig_settp","sig_trail"
   };
   for(int i=0;i<ArraySize(names);i++) UI65Delete(names[i]);
  }

void UI65DeleteSettingsPanel()
  {
   string names[]={"settings_conn","settings_trade","settings_risk","settings_system"};
   for(int i=0;i<ArraySize(names);i++) UI65Delete(names[i]);
  }

void UI65ShowSetup(const string status="")
  {
   g_setup_required=true;
   UI65DeleteAll();

   string bg=UI65Name("bg");
   string shadow=UI65Name("setup_shadow");
   ObjectCreate(0,shadow,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,shadow,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,shadow,OBJPROP_XDISTANCE,18);
   ObjectSetInteger(0,shadow,OBJPROP_YDISTANCE,23);
   ObjectSetInteger(0,shadow,OBJPROP_XSIZE,430);
   ObjectSetInteger(0,shadow,OBJPROP_YSIZE,302);
   ObjectSetInteger(0,shadow,OBJPROP_BGCOLOR,C'7,12,17');
   ObjectSetInteger(0,shadow,OBJPROP_BORDER_COLOR,C'7,12,17');
   ObjectSetInteger(0,shadow,OBJPROP_BACK,false);
   ObjectSetInteger(0,shadow,OBJPROP_ZORDER,5);

   ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,12);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,17);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,430);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,302);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,C'16,21,27');
   ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,C'58,70,82');
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,bg,OBJPROP_ZORDER,10);

   string mode=InpAdminMode?"ADMIN TERMINAL":"CUSTOMER TERMINAL";
   UI65Label("title","NEXUS AUTO TRADE",28,34,14,clrWhite);
   UI65Label("mode",mode,28,58,9,InpAdminMode?C'93,216,154':C'120,190,255');
   UI65Label("status",status==""?(InpAdminMode?"Enter administrator token":"Enter your NEXUS license"):status,28,82,9,C'164,178,190');

   if(InpAdminMode)
     {
      UI65Label("admin_lbl","ADMIN TOKEN",28,116,9);
      UI65Edit("admin",EffectiveAdminToken(),28,134,374,32);
      UI65HiddenEdit("license","");
      UI65Label("paste_help","Administrator access is validated by backend account allow-list + token.",28,176,8,C'150,165,178');
     }
   else
     {
      UI65Label("license_lbl","LICENSE KEY",28,116,9);
      UI65Edit("license",g_license_key,28,134,374,32);
      UI65HiddenEdit("admin","");
      UI65Label("paste_help","Paste your license. Admin credentials are never shown in customer mode.",28,176,8,C'150,165,178');
     }

   UI65Label("locked1","FAIL-CLOSED ACCESS",28,205,9,C'255,196,96');
   UI65Label("locked2","No valid authorization = no new trades.",28,224,8,C'164,178,190');
   UI65Button("connect","CONNECT & ACTIVATE",28,254,250,38,C'31,132,91');
   UI65Button("reset","CLEAR",287,254,115,38,C'147,49,57');
   ChartRedraw();
  }

int UI65NexusPositions()
  {
   int count=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if((long)PositionGetInteger(POSITION_MAGIC)==InpMagicNumber) count++;
     }
   return count;
  }

int UI65NexusOrders()
  {
   int count=0;
   for(int i=OrdersTotal()-1;i>=0;i--)
     {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0 || !OrderSelect(ticket)) continue;
      if((long)OrderGetInteger(ORDER_MAGIC)==InpMagicNumber) count++;
     }
   return count;
  }

bool UI65CanReview(string &reason)
  {
   string symbol=UI65Text("sig_symbol",g_admin_signal_symbol);
   double sl=StringToDouble(UI65Text("sig_sl","0"));
   double tp1=StringToDouble(UI65Text("sig_tp1","0"));
   double risk=StringToDouble(UI65Text("sig_risk","0"));
   double entry=StringToDouble(UI65Text("sig_entry","0"));
   if(symbol=="") { reason="SYMBOL IS REQUIRED"; return false; }
   if(sl<=0) { reason="STOP LOSS IS REQUIRED"; return false; }
   if(tp1<=0) { reason="TP1 IS REQUIRED"; return false; }
   if(risk<=0) { reason="RISK MUST BE ABOVE ZERO"; return false; }
   if(g_admin_signal_order=="LIMIT" && entry<=0) { reason="LIMIT ENTRY IS REQUIRED"; return false; }
   if(g_manual_destination!="FREE" && g_manual_destination!="VIP" && g_manual_destination!="BOTH")
     { reason="SELECT FREE / VIP / BOTH"; return false; }
   reason="";
   return true;
  }

string UI65ReviewLine1()
  {
   return g_admin_signal_direction+"  "+g_admin_signal_order+"  |  "+UI65Text("sig_symbol",g_admin_signal_symbol)+
          "  |  ENTRY "+UI65Text("sig_entry","MARKET")+"  |  SL "+UI65Text("sig_sl","—");
  }

string UI65ReviewLine2()
  {
   return "TP1 "+UI65Text("sig_tp1","—")+"  |  RISK "+UI65Text("sig_risk","—")+"%  |  "+
          g_admin_trailing_profile+"  |  DEST "+g_manual_destination;
  }

void UI65PaintSignalPanel()
  {
   UI65DeleteTradePanel();
   UI65DeleteSettingsPanel();
   ObjectSetString(0,UI65Name("status_body"),OBJPROP_TEXT,"");

   string v_symbol=UI65Text("sig_symbol",g_admin_signal_symbol);
   string v_entry=UI65Text("sig_entry","");
   string v_sl=UI65Text("sig_sl","");
   string v_tp1=UI65Text("sig_tp1","");
   string v_tp2=UI65Text("sig_tp2","");
   string v_tp3=UI65Text("sig_tp3","");
   string v_tp4=UI65Text("sig_tp4","");
   string v_tp5=UI65Text("sig_tp5","");
   string v_risk=UI65Text("sig_risk","1");
   string v_lot=UI65Text("sig_lot",DoubleToString(g_admin_fixed_lot,2));

   UI65Delete("sig_min");
   UI65Delete("sig_manage_title"); UI65Delete("sig_manage_id_lbl"); UI65Delete("sig_manage_id");
   UI65Delete("sig_manage_value_lbl"); UI65Delete("sig_manage_value");
   UI65Delete("sig_be"); UI65Delete("sig_close"); UI65Delete("sig_cancel");
   UI65Delete("sig_setsl"); UI65Delete("sig_settp"); UI65Delete("sig_trail");

   UI65Label("sig_title","NEW SIGNAL",28,102,13,clrWhite);
   UI65Label("sig_legacy","ORDER DETAILS",28,128,8,C'132,151,166');
   UI65Label("sig_sub","HOST  "+_Symbol+"   •   CANONICAL  "+CanonicalSignalSymbol(_Symbol),28,146,8,C'132,151,166');

   UI65Label("sig_symbol_lbl","SYMBOL",28,172,8); UI65Edit("sig_symbol",v_symbol,28,188,122,28);
   UI65Label("sig_entry_lbl","ENTRY",160,172,8); UI65Edit("sig_entry",v_entry,160,188,112,28);
   UI65Label("sig_sl_lbl","STOP LOSS",282,172,8); UI65Edit("sig_sl",v_sl,282,188,112,28);

   UI65Label("sig_tp1_lbl","TP1",28,228,8); UI65Edit("sig_tp1",v_tp1,28,244,112,28);
   UI65Label("sig_tp2_lbl","TP2",150,228,8); UI65Edit("sig_tp2",v_tp2,150,244,112,28);
   UI65Label("sig_tp3_lbl","TP3",272,228,8); UI65Edit("sig_tp3",v_tp3,272,244,112,28);

   UI65Label("sig_tp4_lbl","TP4",28,284,8); UI65Edit("sig_tp4",v_tp4,28,300,112,28);
   UI65Label("sig_tp5_lbl","TP5",150,284,8); UI65Edit("sig_tp5",v_tp5,150,300,112,28);
   UI65Label("sig_risk_lbl","RISK %",272,284,8); UI65Edit("sig_risk",v_risk,272,300,112,28);

   UI65Button("sig_buy","BUY",28,342,78,28,g_admin_signal_direction=="BUY"?C'31,132,91':C'48,57,66');
   UI65Button("sig_sell","SELL",112,342,78,28,g_admin_signal_direction=="SELL"?C'163,56,66':C'48,57,66');
   UI65Button("sig_market","MARKET",202,342,88,28,g_admin_signal_order=="MARKET"?C'37,108,162':C'48,57,66');
   UI65Button("sig_limit","LIMIT",296,342,88,28,g_admin_signal_order=="LIMIT"?C'37,108,162':C'48,57,66');

   UI65Label("sig_size_lbl","SIZING",28,382,8);
   UI65Button("sig_size_risk","RISK",28,398,86,26,g_admin_sizing_mode=="RISK"?C'31,132,91':C'48,57,66');
   UI65Button("sig_size_fixed","FIXED",120,398,86,26,g_admin_sizing_mode=="FIXED"?C'31,132,91':C'48,57,66');
   UI65Edit("sig_lot",v_lot,216,398,92,26);
   UI65Label("sig_lot_hint","FIXED LOT",316,405,7,C'132,151,166');

   UI65Label("sig_trail_lbl","TRAILING PROFILE",28,438,8);
   for(int ti=1;ti<=7;ti++)
     {
      string tn="sig_trail_"+StringFormat("%02d",ti);
      int tx=28+(ti-1)*54;
      UI65Button(tn,StringFormat("T%02d",ti),tx,454,50,25,g_admin_trailing_profile==NexusTrailingCode(ti)?C'31,132,91':C'48,57,66');
     }

   UI65Label("sig_dest_lbl","CHANNEL / ACCESS",28,494,8);
   UI65Button("sig_dest_free","FREE",28,510,112,26,g_manual_destination=="FREE"?C'37,108,162':C'48,57,66');
   UI65Button("sig_dest_vip","VIP",146,510,112,26,g_manual_destination=="VIP"?C'113,76,168':C'48,57,66');
   UI65Button("sig_dest_both","BOTH",264,510,120,26,g_manual_destination=="BOTH"?C'31,132,91':C'48,57,66');
   UI65Label("sig_dest_state","SELECTED  "+(g_manual_destination=="NONE"?"NONE":g_manual_destination),394,517,7,C'132,151,166');

   if(!g_ui65_reviewing)
     {
      UI65Delete("sig_issue"); UI65Delete("sig_review_back"); UI65Delete("sig_review_summary"); UI65Delete("sig_review_summary2");
      UI65Button("sig_review","REVIEW SIGNAL",28,566,480,38,C'31,132,91');
     }
   else
     {
      UI65Delete("sig_review");
      UI65Label("sig_review_summary",UI65ReviewLine1(),28,552,8,C'198,214,224');
      UI65Label("sig_review_summary2",UI65ReviewLine2(),28,570,8,C'198,214,224');
      UI65Button("sig_review_back","EDIT",28,598,112,38,C'48,57,66');
      UI65Button("sig_issue",g_admin_signal_busy?"ISSUING...":"CONFIRM & ISSUE",146,598,362,38,C'31,132,91');
     }
  }

void UI65PaintTradePanel()
  {
   UI65DeleteSignalPanel();
   UI65DeleteSettingsPanel();
   ObjectSetString(0,UI65Name("status_body"),OBJPROP_TEXT,"");

   UI65Label("trade_title",g_access_mode==NEXUS_ADMIN?"TRADES / MANAGEMENT":"MY TRADES",28,106,13,clrWhite);
   UI65Label("trade_meta","OPEN  "+IntegerToString(UI65NexusPositions())+"   •   PENDING  "+IntegerToString(UI65NexusOrders()),28,135,9,C'132,151,166');
   UI65Label("trade_state","LAST  "+(g_last_exec_signal==""?"—":g_last_exec_signal)+"   •   "+g_last_exec_state+"   •   "+(g_last_exec_symbol==""?"—":g_last_exec_symbol),28,158,9);

   if(g_access_mode!=NEXUS_ADMIN)
     {
      UI65Label("trade_hint","Trade management is controlled by NEXUS policy. Customer mode is view-only.",28,195,9,C'164,178,190');
      return;
     }

   string v_id=UI65Text("sig_manage_id",g_admin_manage_id);
   string v_value=UI65Text("sig_manage_value",g_admin_manage_value);
   UI65Label("sig_manage_title","SIGNAL COMMAND",28,202,9,C'198,214,224');
   UI65Label("sig_manage_id_lbl","SIGNAL ID",28,228,8); UI65Edit("sig_manage_id",v_id,28,244,150,30);
   UI65Label("sig_manage_value_lbl","VALUE",188,228,8); UI65Edit("sig_manage_value",v_value,188,244,120,30);
   UI65Label("trade_hint","Value is required only for UPDATE SL / UPDATE TP.",318,252,7,C'132,151,166');

   UI65Button("sig_be","MOVE TO BE",28,294,112,30,C'37,108,162');
   UI65Button("sig_setsl","UPDATE SL",146,294,112,30,C'48,57,66');
   UI65Button("sig_settp","UPDATE TP",264,294,112,30,C'48,57,66');
   UI65Button("sig_trail","ACTIVATE TRAIL",382,294,126,30,C'48,57,66');
   UI65Button("sig_cancel","CANCEL PENDING",28,338,230,34,C'138,94,36');
   UI65Button("sig_close","CLOSE POSITION",278,338,230,34,C'147,49,57');

   if(g_ui65_confirm_command!="")
     {
      string action=(g_ui65_confirm_command=="CLOSE_SIGNAL"?"CLOSE POSITION":"CANCEL PENDING ORDER");
      UI65Label("trade_confirm_text","CONFIRM DESTRUCTIVE ACTION: "+action,28,398,9,C'255,184,92');
      UI65Button("trade_abort","GO BACK",28,426,150,34,C'48,57,66');
      UI65Button("trade_confirm","CONFIRM",188,426,320,34,C'147,49,57');
     }
   else
     {
      UI65Delete("trade_confirm_text"); UI65Delete("trade_abort"); UI65Delete("trade_confirm");
     }
  }

string UI65SettingsBody()
  {
   string api_ok=(g_api.LastHttpStatus()>=200&&g_api.LastHttpStatus()<300?"✓":"✕");
   string mt5_ok=(TerminalInfoInteger(TERMINAL_CONNECTED)?"✓":"✕");
   string account_ok=(g_account_verified?"✓":"✕");
   string auth_ok=(g_access_mode==NEXUS_ADMIN?(g_admin_authenticated?"✓":"✕"):(g_license_active?"✓":"✕"));
   string new_ok=(g_allow_new&&InpAllowNewTrades?"✓":"✕");
   string manage_ok=(g_allow_manage&&InpManageExistingTrades?"✓":"✕");
   string trade_ok=(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)?"✓":"✕");

   if(g_panel_tab==1)
      return "API         "+api_ok+"   HTTP        "+IntegerToString(g_api.LastHttpStatus())+
             "\nMT5         "+mt5_ok+"   ACCOUNT     "+account_ok+
             "\nAUTH MODE   "+(g_access_mode==NEXUS_ADMIN?"ADMIN":"LICENSE")+"   AUTH        "+auth_ok+
             "\nHEARTBEAT   "+(g_last_heartbeat>0?"✓":"—")+"   POLL        "+IntegerToString(InpPollSeconds)+"s";

   if(g_panel_tab==2)
      return "NEW TRADES  "+new_ok+"   MANAGE      "+manage_ok+
             "\nTERMINAL    "+trade_ok+"   MAGIC       "+(string)InpMagicNumber+
             "\nLAST SIGNAL "+(g_last_exec_signal==""?"—":g_last_exec_signal)+
             "\nSTATE       "+g_last_exec_state+"   VOLUME      "+(g_last_exec_volume>0?DoubleToString(g_last_exec_volume,2):"—")+
             "\nBROKER      "+(g_last_exec_symbol==""?"—":g_last_exec_symbol)+
             "\nERROR       "+(g_last_exec_reason==""?"—":g_last_exec_reason);

   if(g_panel_tab==3)
      return "POLICY       NEXUS LOCKED"+
             "\nMANAGEMENT   "+manage_ok+"   TRAILING    "+(manage_ok=="✓"?"ON":"OFF")+
             "\nTRAIL TF     "+EnumToString(InpTrailingTimeframe)+
             "\nMANUAL TRAIL "+NexusTrailingCode((int)InpManualTrailingProfile)+
             "\nMANUAL MGMT  "+(InpManageManualTrades?"ON":"OFF");

   string cap_symbol=(g_last_exec_symbol==""?_Symbol:g_last_exec_symbol);
   long cap_trade_mode=SymbolInfoInteger(cap_symbol,SYMBOL_TRADE_MODE);
   long cap_order_mode=SymbolInfoInteger(cap_symbol,SYMBOL_ORDER_MODE);
   long cap_filling=SymbolInfoInteger(cap_symbol,SYMBOL_FILLING_MODE);
   long cap_stops=SymbolInfoInteger(cap_symbol,SYMBOL_TRADE_STOPS_LEVEL);
   long cap_freeze=SymbolInfoInteger(cap_symbol,SYMBOL_TRADE_FREEZE_LEVEL);
   int cap_digits=(int)SymbolInfoInteger(cap_symbol,SYMBOL_DIGITS);
   double cap_point=SymbolInfoDouble(cap_symbol,SYMBOL_POINT);
   double cap_tick_size=SymbolInfoDouble(cap_symbol,SYMBOL_TRADE_TICK_SIZE);
   double cap_tick_value=SymbolInfoDouble(cap_symbol,SYMBOL_TRADE_TICK_VALUE);
   double cap_min=SymbolInfoDouble(cap_symbol,SYMBOL_VOLUME_MIN);
   double cap_step=SymbolInfoDouble(cap_symbol,SYMBOL_VOLUME_STEP);
   double cap_max=SymbolInfoDouble(cap_symbol,SYMBOL_VOLUME_MAX);
   return "EA VERSION    "+NEXUS_EA_VERSION+
          "\nAPI HTTP      "+IntegerToString(g_api.LastHttpStatus())+
          "\nACCOUNT       "+(string)AccountInfoInteger(ACCOUNT_LOGIN)+
          "\nBROKER        "+AccountInfoString(ACCOUNT_COMPANY)+
          "\nSERVER        "+AccountInfoString(ACCOUNT_SERVER)+
          "\nEXEC SYMBOL   "+cap_symbol+" | CANON "+CanonicalSignalSymbol(cap_symbol)+
          "\nTRADE MODE    "+(string)cap_trade_mode+" | ORDER MODE "+(string)cap_order_mode+
          "\nFILLING       "+(string)cap_filling+" | DIGITS "+(string)cap_digits+
          "\nPOINT         "+DoubleToString(cap_point,cap_digits)+" | TICK SIZE "+DoubleToString(cap_tick_size,cap_digits)+
          "\nTICK VALUE    "+DoubleToString(cap_tick_value,8)+
          "\nVOLUME        MIN "+DoubleToString(cap_min,4)+" STEP "+DoubleToString(cap_step,4)+" MAX "+DoubleToString(cap_max,4)+
          "\nSTOPS/FREEZE  "+(string)cap_stops+" / "+(string)cap_freeze+
          "\nLAST ERROR    "+(g_last_exec_reason==""?"—":g_last_exec_reason);
  }

void UI65PaintSettingsPanel()
  {
   UI65DeleteSignalPanel();
   UI65DeleteTradePanel();
   if(g_panel_tab!=1 && g_panel_tab!=2 && g_panel_tab!=3 && g_panel_tab!=5) g_panel_tab=1;

   UI65Button("settings_conn","CONNECTION",28,104,110,26,g_panel_tab==1?C'31,132,91':C'48,57,66');
   UI65Button("settings_trade","TRADING",144,104,98,26,g_panel_tab==2?C'31,132,91':C'48,57,66');
   UI65Button("settings_risk","RISK",248,104,78,26,g_panel_tab==3?C'31,132,91':C'48,57,66');
   UI65Button("settings_system","SYSTEM",332,104,92,26,g_panel_tab==5?C'31,132,91':C'48,57,66');
   UI65Label("status_body",UI65SettingsBody(),28,150,10,clrWhite);
   ObjectSetString(0,UI65Name("status_body"),OBJPROP_FONT,"Consolas");
  }

void UI65PaintStatusPanel()
  {
   if(g_setup_required) return;
   if(g_access_mode!=NEXUS_ADMIN && g_panel_tab==4) g_panel_tab=0;

   int chart_w=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   int panel_w=g_panel_minimized?390:MathMin(560,MathMax(520,chart_w-24));
   int panel_h=430;
   if(g_access_mode==NEXUS_ADMIN && g_panel_tab==4) panel_h=660;
   else if(g_panel_tab==6) panel_h=(g_access_mode==NEXUS_ADMIN?500:300);

   string shadow=UI65Name("status_shadow");
   string bg=UI65Name("status_bg");
   if(ObjectFind(0,shadow)<0) ObjectCreate(0,shadow,OBJ_RECTANGLE_LABEL,0,0,0);
   if(ObjectFind(0,bg)<0) ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);

   ObjectSetInteger(0,shadow,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,shadow,OBJPROP_XDISTANCE,16);
   ObjectSetInteger(0,shadow,OBJPROP_YDISTANCE,17);
   ObjectSetInteger(0,shadow,OBJPROP_XSIZE,panel_w);
   ObjectSetInteger(0,shadow,OBJPROP_YSIZE,panel_h);
   ObjectSetInteger(0,shadow,OBJPROP_BGCOLOR,C'7,12,17');
   ObjectSetInteger(0,shadow,OBJPROP_BORDER_COLOR,C'7,12,17');
   ObjectSetInteger(0,shadow,OBJPROP_BACK,false);
   ObjectSetInteger(0,shadow,OBJPROP_ZORDER,5);

   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,12);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,12);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,panel_w);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,panel_h);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,C'16,21,27');
   ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,C'58,70,82');
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTED,false);
   ObjectSetInteger(0,bg,OBJPROP_ZORDER,10);

   UI65Label("status_title","NEXUS  |  "+(g_access_mode==NEXUS_ADMIN?"ADMIN":"USER"),28,22,12,clrWhite);
   UI65Label("status_meta",(TerminalInfoInteger(TERMINAL_CONNECTED)?"● ONLINE":"● OFFLINE")+"   •   "+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"   •   "+_Symbol,188,25,8,TerminalInfoInteger(TERMINAL_CONNECTED)?C'93,216,154':C'222,93,105');
   UI65Button("status_min",g_panel_minimized?"+":"—",panel_w-46,18,30,24,C'48,57,66');

   if(g_panel_minimized)
     {
      for(int i=0;i<3;i++) UI65Delete("status_tab"+IntegerToString(i));
      UI65DeleteSignalPanel(); UI65DeleteTradePanel(); UI65DeleteSettingsPanel();
      UI65Label("status_body",(g_allow_new?"READY":"LOCKED"),28,25,9,g_allow_new?C'93,216,154':C'222,93,105');
      ChartRedraw();
      return;
     }

   string tab0=(g_access_mode==NEXUS_ADMIN?"NEW SIGNAL":"OVERVIEW");
   int active_main=(g_panel_tab==6?1:((g_access_mode==NEXUS_ADMIN && g_panel_tab==4)||(g_access_mode!=NEXUS_ADMIN && g_panel_tab==0)?0:2));
   UI65Button("status_tab0",tab0,24,60,158,30,active_main==0?C'31,132,91':C'48,57,66');
   UI65Button("status_tab1","TRADES",188,60,150,30,active_main==1?C'31,132,91':C'48,57,66');
   UI65Button("status_tab2","SETTINGS",344,60,150,30,active_main==2?C'31,132,91':C'48,57,66');

   if(g_access_mode==NEXUS_ADMIN && g_panel_tab==4)
      UI65PaintSignalPanel();
   else if(g_panel_tab==6)
      UI65PaintTradePanel();
   else if(g_access_mode!=NEXUS_ADMIN && g_panel_tab==0)
     {
      UI65DeleteSignalPanel(); UI65DeleteTradePanel(); UI65DeleteSettingsPanel();
      string overview="ACCOUNT      "+(string)AccountInfoInteger(ACCOUNT_LOGIN)+
                      "\nMODE         "+(g_license_active?"LICENSED":"LOCKED")+
                      "\nOPEN         "+IntegerToString(UI65NexusPositions())+"   PENDING  "+IntegerToString(UI65NexusOrders())+
                      "\nLAST SIGNAL  "+(g_last_exec_signal==""?"—":g_last_exec_signal)+
                      "\nSTATE        "+g_last_exec_state+
                      "\nBROKER       "+(g_last_exec_symbol==""?"—":g_last_exec_symbol)+
                      "\nAUTO MGMT    "+((g_allow_manage&&InpManageExistingTrades)?"ON":"OFF");
      UI65Label("status_body",overview,28,112,10,clrWhite);
      ObjectSetString(0,UI65Name("status_body"),OBJPROP_FONT,"Consolas");
     }
   else
      UI65PaintSettingsPanel();

   ChartRedraw();
  }

void UI65RefreshAfterCore()
  {
   if(g_setup_required)
     {
      string status="";
      if(ObjectFind(0,UI65Name("status"))>=0) status=ObjectGetString(0,UI65Name("status"),OBJPROP_TEXT);
      if(status!="") g_ui65_setup_status=status;
      UI65ShowSetup(g_ui65_setup_status);
      return;
     }
   UI65PaintStatusPanel();
  }

int OnInit()
  {
   int rc=NEXUSCore_OnInit();
   if(g_setup_required)
     {
      string status=UI65Text("status",InpAdminMode?"Enter administrator token":"Enter your NEXUS license");
      g_ui65_setup_status=status;
      UI65ShowSetup(status);
     }
   else
     {
      g_panel_tab=(g_access_mode==NEXUS_ADMIN?4:0);
      UI65PaintStatusPanel();
     }
   return rc;
  }

void OnDeinit(const int reason)
  {
   NEXUSCore_OnDeinit(reason);
   UI65DeleteAll();
  }

void OnTimer()
  {
   NEXUSCore_OnTimer();
   if(!g_setup_required) UI65PaintStatusPanel();
  }

void OnTick()
  {
   // Trading and trailing remain 100% inside the hardened core.
   // No WebRequest, screenshot capture or UI repaint is introduced on ticks.
   NEXUSCore_OnTick();
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   NEXUSCore_OnTradeTransaction(trans,request,result);
   if(!g_setup_required) UI65PaintStatusPanel();
  }

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
  {
   if(id==CHARTEVENT_OBJECT_ENDEDIT)
     {
      if(sparam==UI65Name("sig_manage_id"))
        { g_admin_manage_id=ObjectGetString(0,sparam,OBJPROP_TEXT); return; }
      if(sparam==UI65Name("sig_manage_value"))
        { g_admin_manage_value=ObjectGetString(0,sparam,OBJPROP_TEXT); return; }
     }

   if(id==CHARTEVENT_OBJECT_CLICK && !g_setup_required)
     {
      if(sparam==UI65Name("status_tab0"))
        {
         g_panel_tab=(g_access_mode==NEXUS_ADMIN?4:0);
         g_ui65_reviewing=false; g_ui65_confirm_command="";
         UI65PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("status_tab1"))
        {
         g_panel_tab=6; g_ui65_reviewing=false; g_ui65_confirm_command="";
         UI65PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("status_tab2"))
        {
         g_panel_tab=1; g_ui65_reviewing=false; g_ui65_confirm_command="";
         UI65PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("sig_review"))
        {
         string reason="";
         if(!UI65CanReview(reason))
           { g_last_exec_reason=reason; UI65Label("sig_review_summary",reason,28,548,8,C'222,93,105'); ChartRedraw(); }
         else
           { g_ui65_reviewing=true; UI65PaintStatusPanel(); }
         ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("sig_review_back"))
        {
         g_ui65_reviewing=false; UI65PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("sig_issue") && g_ui65_reviewing)
        {
         IssueAdminSignal(); g_ui65_reviewing=false; UI65PaintStatusPanel();
         ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("sig_close"))
        {
         g_ui65_confirm_command="CLOSE_SIGNAL"; UI65PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("sig_cancel"))
        {
         g_ui65_confirm_command="CANCEL_PENDING"; UI65PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("trade_abort"))
        {
         g_ui65_confirm_command=""; UI65PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
      if(sparam==UI65Name("trade_confirm"))
        {
         string command=g_ui65_confirm_command; g_ui65_confirm_command="";
         if(command!="") IssueAdminCommand(command);
         UI65PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
     }

   // All non-visual behavior remains delegated to the production event handler:
   // activation, signal direction/order selection, trailing profile, sizing,
   // destination, settings sub-tabs and non-destructive management commands.
   NEXUSCore_OnChartEvent(id,lparam,dparam,sparam);

   if(g_setup_required)
     {
      string status=UI65Text("status",g_ui65_setup_status);
      if(status!="") g_ui65_setup_status=status;
      UI65ShowSetup(g_ui65_setup_status);
     }
   else
      UI65PaintStatusPanel();
  }

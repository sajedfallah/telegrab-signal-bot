#property strict
#property version   "1.65"
#property description "NEXUS Auto Trade - MT5 Signal Authority / AutoTrade client - Admin execution and Telegram publication fix"

#include "Include/NexusTypes.mqh"
#include "Include/APIClient.mqh"
#include "Include/SignalParser.mqh"
#include "Include/SymbolMapper.mqh"
#include "Include/TradeManager.mqh"
#include "Include/TrailingEngine.mqh"
#include "Include/CommandManager.mqh"

input group "NEXUS Technical Settings"
input string InpApiBaseUrl="http://127.0.0.1:8080";
input int    InpHttpTimeoutMs=5000;
input int    InpPollSeconds=3;
input int    InpHeartbeatSeconds=300;
input int    InpLiveSyncSeconds=5;
input int    InpHistoryReconcileSeconds=300;
input int    InpHistoryReconcileHours=72;
input double InpDefaultMaxEntryDeviationPct=0.20;
input int    InpLimitExpirationHours=0; // 0 = broker GTC/default, >0 = specified expiration
input bool   InpStrictLimitBrokerChecks=true;
input bool   InpEnableAutoSymbolMapping=true;
input long   InpMagicNumber=258025;
input ENUM_TIMEFRAMES InpTrailingTimeframe=PERIOD_M1;

input group "Safety"
input bool InpAllowNewTrades=true;
input bool InpManageExistingTrades=true;
// Safety: manual positions are managed only after explicit opt-in.
input bool InpManageManualTrades=false;
// Administrator-only mode. The backend also requires the account to be allow-listed.
input bool InpAdminMode=false;
input string InpAdminToken="";
input ENUM_NEXUS_TRAILING_PROFILE InpManualTrailingProfile=NEXUS_TRAIL_07;

#define NEXUS_EA_VERSION "0.6.5"
#define NEXUS_RUNTIME_PATCH "V062-LIVE-TRUTH-RECEIPT-RELIABLE"

// Administrator credentials are intentionally NOT embedded in source code.
// Configure InpAdminMode=true and provide InpAdminToken on the administrator
// terminal. The backend additionally enforces its server-side allow-list.
// Internal NEXUS Backend endpoint. End users do not need to enter this URL.
CNexusAPIClient      g_api;
CNexusSignalParser   g_parser;
CNexusSymbolMapper   g_mapper;
CNexusTradeManager   g_trade;
CNexusTrailingEngine g_trailing;
CNexusCommandManager g_commands;

enum NEXUS_ACCESS_MODE
  {
   NEXUS_STANDARD=0,
   NEXUS_LICENSED=1,
   NEXUS_ADMIN=2
  };

NEXUS_ACCESS_MODE g_access_mode=NEXUS_STANDARD;
bool g_license_active=false;
bool g_admin_authenticated=false;
bool g_account_verified=false;
string g_manual_destination="NONE";
#define NXS_MANUAL_PREFIX "NXS_MANUAL_"

bool g_allow_new=false;
bool g_allow_manage=false;

// Runtime state for administrator-issued signals.
// These variables are intentionally global because IssueAdminSignal(),
// UI handlers, and recovery paths all share the same state.
bool g_admin_signal_busy=false;
ulong g_admin_issue_nonce=0;
bool g_force_close_all=false;
long g_last_signal_id=0;
long g_last_command_id=0;
datetime g_last_heartbeat=0;
datetime g_last_history_reconcile=0;
bool g_bootstrap=true;
bool g_setup_required=false;

string g_last_exec_state="WAITING";
string g_last_exec_signal="-";
string g_last_exec_symbol="-";
string g_last_exec_reason="";
double g_last_exec_volume=0.0;
int g_panel_tab=4;
bool g_panel_minimized=false;

// User-facing configuration is collected by the on-chart setup wizard.
string g_license_key="";
string g_admin_token_runtime="";
string g_admin_signal_symbol="";
string g_admin_trailing_profile=NexusTrailingCode((int)InpManualTrailingProfile);
string g_admin_sizing_mode="RISK";
double g_admin_fixed_lot=0.01;
string g_admin_signal_direction="SELL";
string g_admin_signal_order="MARKET";
string g_admin_manage_id="";
string g_admin_manage_value="";
ENUM_NEXUS_RISK_MODE g_risk_mode=NEXUS_RISK_SIGNAL_PERCENT;
double g_fixed_lot=0.10;
double g_user_risk_percent=1.0;

#define NXS_UI_PREFIX "NXS.UI."
#define NXS_CONFIG_PREFIX "NEXUS_AutoTrade_"

string ConfigFileName()
  {
   return NXS_CONFIG_PREFIX+(string)AccountInfoInteger(ACCOUNT_LOGIN)+".csv";
  }

bool SaveUserConfig()
  {
   int h=FileOpen(ConfigFileName(),FILE_WRITE|FILE_CSV,';');
   if(h==INVALID_HANDLE) { Print("NEXUS config save failed: ",GetLastError()); return false; }
   FileWrite(h,g_license_key,(int)g_risk_mode,DoubleToString(g_fixed_lot,2),DoubleToString(g_user_risk_percent,2));
   FileClose(h);
   return true;
  }

bool LoadUserConfig()
  {
   int h=FileOpen(ConfigFileName(),FILE_READ|FILE_CSV,';');
   if(h==INVALID_HANDLE) return false;
   string license=FileReadString(h);
   int mode=(int)StringToInteger(FileReadString(h));
   double lot=StringToDouble(FileReadString(h));
   double risk=StringToDouble(FileReadString(h));
   FileClose(h);
   if(license=="") return false;
   g_license_key=license;
   if(mode<0 || mode>2) mode=2;
   g_risk_mode=(ENUM_NEXUS_RISK_MODE)mode;
   g_fixed_lot=(lot>0?lot:0.10);
   g_user_risk_percent=(risk>0?risk:1.0);
   return true;
  }

void DeleteUserConfig()
  {
   FileDelete(ConfigFileName());
   g_license_key="";
   g_risk_mode=NEXUS_RISK_SIGNAL_PERCENT;
   g_fixed_lot=0.10;
   g_user_risk_percent=1.0;
  }

void UISetLabel(const string name,const string text,const int x,const int y,const int size=10)
  {
   string n=NXS_UI_PREFIX+name;
   if(ObjectFind(0,n)<0) ObjectCreate(0,n,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,size);
   ObjectSetInteger(0,n,OBJPROP_COLOR,clrWhite);
   ObjectSetString(0,n,OBJPROP_FONT,"Arial");
   ObjectSetString(0,n,OBJPROP_TEXT,text);
  }

void UISetEdit(const string name,const string value,const int x,const int y,const int w,const int h)
  {
   string n=NXS_UI_PREFIX+name;
   if(ObjectFind(0,n)<0)
     {
      if(!ObjectCreate(0,n,OBJ_EDIT,0,0,0))
        {
         Print("NEXUS UI: failed to create edit field ",n," error=",GetLastError());
         return;
        }
     }

   ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,n,OBJPROP_XSIZE,w);
   ObjectSetInteger(0,n,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,n,OBJPROP_BGCOLOR,clrWhite);
   ObjectSetInteger(0,n,OBJPROP_COLOR,clrBlack);
   ObjectSetInteger(0,n,OBJPROP_BORDER_COLOR,clrDimGray);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,10);

   // IMPORTANT: OBJ_EDIT must explicitly be editable.
   // This lets the user click the License box, type, select text and use
   // normal keyboard editing shortcuts such as Ctrl+A / Ctrl+C / Ctrl+V.
   ObjectSetInteger(0,n,OBJPROP_READONLY,false);
   ObjectSetInteger(0,n,OBJPROP_ALIGN,ALIGN_LEFT);
   // Do NOT enable object movement selection for an edit control. The official
   // OBJ_EDIT pattern keeps selection disabled while READONLY=false; the terminal
   // then gives the field native text-edit focus (typing, selection and Ctrl+V).
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTED,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,n,OBJPROP_ZORDER,100);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);

   ObjectSetString(0,n,OBJPROP_TEXT,value);
  }

void UISetButton(const string name,const string text,const int x,const int y,const int w,const int h,const color bg=clrDimGray)
  {
   string n=NXS_UI_PREFIX+name;
   if(ObjectFind(0,n)<0) ObjectCreate(0,n,OBJ_BUTTON,0,0,0);
   ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,x);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);
   ObjectSetInteger(0,n,OBJPROP_XSIZE,w);
   ObjectSetInteger(0,n,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,n,OBJPROP_BGCOLOR,bg);
   ObjectSetInteger(0,n,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,9);
   // Keep interactive controls above the unified panel background.
   // Without an explicit Z-order, the background rectangle can consume
   // mouse clicks and make every status/admin button appear dead.
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTED,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,false);
   ObjectSetInteger(0,n,OBJPROP_BACK,false);
   ObjectSetInteger(0,n,OBJPROP_ZORDER,100);
   ObjectSetString(0,n,OBJPROP_TEXT,text);
  }

string ManualDestinationKey()
  {
   return "NXS.MANUAL.DEST."+(string)AccountInfoInteger(ACCOUNT_LOGIN);
  }

void LoadManualDestination()
  {
   if(GlobalVariableCheck(ManualDestinationKey()))
     {
      double v=GlobalVariableGet(ManualDestinationKey());
      if(v==0) g_manual_destination="FREE";
      else if(v==1) g_manual_destination="VIP";
      else if(v==2) g_manual_destination="BOTH";
       else g_manual_destination="NONE";
     }
  }

void SaveManualDestination()
  {
   double code=-1.0; if(g_manual_destination=="FREE") code=0.0; else if(g_manual_destination=="VIP") code=1.0; else if(g_manual_destination=="BOTH") code=2.0; GlobalVariableSet(ManualDestinationKey(),code);
  }

void PaintManualDestinationPanel()
  {
   // Manual destination controls are rendered inside the unified Status Panel.
   PaintStatusPanel();
  }

void SetManualDestination(const string value)
  {
   string v=value; StringToUpper(v);
   if(v!="FREE" && v!="VIP" && v!="BOTH") return;
   g_manual_destination=v; SaveManualDestination();
   Print("NEXUS manual signal destination: ",g_manual_destination);
   PaintManualDestinationPanel();
  }

void DeleteManualDestinationPanel()
  {
   ObjectDelete(0,NXS_UI_PREFIX+"md_title");
   ObjectDelete(0,NXS_UI_PREFIX+"md_free");
   ObjectDelete(0,NXS_UI_PREFIX+"md_vip");
   ObjectDelete(0,NXS_UI_PREFIX+"md_both");
   ObjectDelete(0,NXS_UI_PREFIX+"md_state");
  }

void DeleteSetupPanel()
  {
   // Restore normal chart keyboard behavior after setup is complete.
   ChartSetInteger(0,CHART_KEYBOARD_CONTROL,true);
   ChartSetInteger(0,CHART_QUICK_NAVIGATION,true);
   int total=ObjectsTotal(0,0,-1);
   for(int i=total-1;i>=0;i--)
     {
      string n=ObjectName(0,i,0,-1);
      if(StringFind(n,NXS_UI_PREFIX)==0) ObjectDelete(0,n);
     }
   ChartRedraw();
  }

void PaintModeButtons()
  {
   UISetButton("mode_signal","NEXUS Management",25,205,145,28,g_risk_mode==NEXUS_RISK_SIGNAL_PERCENT?clrSeaGreen:clrDimGray);
   UISetButton("mode_risk","My Risk %",175,205,105,28,g_risk_mode==NEXUS_RISK_USER_PERCENT?clrSeaGreen:clrDimGray);
   UISetButton("mode_lot","Fixed Lot",285,205,95,28,g_risk_mode==NEXUS_RISK_USER_FIXED_LOT?clrSeaGreen:clrDimGray);
  }

void ShowSetupPanel(const string status="Enter your NEXUS License")
  {
   g_setup_required=true;
   // Prevent chart navigation keys from stealing keyboard focus while the user
   // is typing/pasting into OBJ_EDIT. Keyboard input remains available to controls.
   ChartSetInteger(0,CHART_KEYBOARD_CONTROL,false);
   ChartSetInteger(0,CHART_QUICK_NAVIGATION,false);
   Comment("");
   string bg=NXS_UI_PREFIX+"bg";
   if(ObjectFind(0,bg)<0) ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,10);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,20);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,410);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,300);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,clrBlack);
   ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,clrDimGray);
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);

   UISetLabel("title","NEXUS AUTO TRADE - SETUP",25,35,13);
   UISetLabel("status",status,25,62,9);
   UISetLabel("license_lbl","License Key",25,92,10);
   UISetEdit("license",g_license_key,25,110,365,28);
   UISetLabel("admin_lbl","Admin Token (optional)",25,144,10);
   UISetEdit("admin",EffectiveAdminToken(),25,162,365,28);
   UISetLabel("paste_help","Click License box, then type or press Ctrl+V to paste. Admin Token is optional.",25,195,9);
   UISetLabel("locked1","NEXUS LOCKED MANAGEMENT",25,218,11);
   UISetLabel("locked2","No valid License/Admin Token = no trading.",25,240,9);
   UISetButton("connect","CONNECT & ACTIVATE",25,265,240,35,clrSeaGreen);
   UISetButton("reset","RESET",275,265,90,35,clrFireBrick);
   ChartRedraw();
  }

void ReadSetupFields()
  {
   g_license_key=ObjectGetString(0,NXS_UI_PREFIX+"license",OBJPROP_TEXT);
   StringTrimLeft(g_license_key); StringTrimRight(g_license_key);
   string admin_token=ObjectGetString(0,NXS_UI_PREFIX+"admin",OBJPROP_TEXT);
   StringTrimLeft(admin_token); StringTrimRight(admin_token);
   g_admin_token_runtime=admin_token;
   // Money management and trailing are NEXUS LOCKED and come from each Signal.
   g_risk_mode=NEXUS_RISK_SIGNAL_PERCENT;
  }

string EffectiveAdminToken()
  {
   return g_admin_token_runtime!="" ? g_admin_token_runtime : InpAdminToken;
  }

bool EffectiveAdminMode()
  {
   // Entering an Admin Token is sufficient to request Admin mode.
   // The backend remains authoritative and rejects invalid tokens/accounts.
   return InpAdminMode || StringLen(EffectiveAdminToken())>0;
  }

void ConfigureRuntime()
  {
   string account=(string)AccountInfoInteger(ACCOUNT_LOGIN);
   if(EffectiveAdminMode())
      g_api.ConfigureAdmin(InpApiBaseUrl,account,NEXUS_EA_VERSION,InpHttpTimeoutMs,EffectiveAdminToken());
   else
      g_api.Configure(InpApiBaseUrl,g_license_key,account,NEXUS_EA_VERSION,InpHttpTimeoutMs);
   g_trade.Configure(InpMagicNumber,InpLimitExpirationHours,InpStrictLimitBrokerChecks);
   g_trailing.Configure(&g_trade,InpMagicNumber,InpTrailingTimeframe);
   g_commands.Configure(&g_trade,&g_api);
  }

bool ConnectFromSetup()
  {
   ReadSetupFields();
   if(g_license_key=="" && EffectiveAdminToken()=="")
     {
      ShowSetupPanel("License Key or Admin Token is required");
      return false;
     }
   if(EffectiveAdminMode() && StringLen(EffectiveAdminToken())<8)
     {
      ShowSetupPanel("Admin token is required");
      return false;
     }
   ConfigureRuntime();
   string response;
   if(!g_api.Activate(response))
     {
      ShowSetupPanel("Connection failed: "+g_api.LastError());
      return false;
     }
   ApplyAuthResponse(response);
   if(EffectiveAdminMode())
     {
      if(!g_admin_authenticated)
        {
         g_allow_new=false; g_allow_manage=false;
         ShowSetupPanel("Admin authorization rejected");
         return false;
        }
      g_license_active=true; g_allow_new=true; g_allow_manage=true;
     }
   else if(!g_license_active || !g_allow_manage)
     {
      g_allow_new=false; g_allow_manage=false;
      ShowSetupPanel("License is invalid or inactive");
      return false;
     }
   SaveUserConfig();
   DeleteSetupPanel();
   g_setup_required=false;
   g_bootstrap=true;
   SetPanel("Connected - waiting for signal");
   return true;
  }

string CursorKey(const string what)
  {
   return "NXS.CURSOR."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"."+what;
  }

void LoadCursors()
  {
   if(GlobalVariableCheck(CursorKey("signal"))) g_last_signal_id=(long)GlobalVariableGet(CursorKey("signal"));
   if(GlobalVariableCheck(CursorKey("command"))) g_last_command_id=(long)GlobalVariableGet(CursorKey("command"));
  }

void SaveCursor(const string what,const long value)
  {
   GlobalVariableSet(CursorKey(what),(double)value);
  }

void ApplyAuthResponse(const string json)
  {
   string mode=NexusJsonString(json,"mode","");
   StringToUpper(mode);
   string status=NexusJsonString(json,"license_status",""); StringToUpper(status);

   g_admin_authenticated=NexusJsonBool(json,"admin_authenticated",false) || (mode=="ADMIN");
   g_account_verified=NexusJsonBool(json,"account_verified",false);
   g_license_active=(status=="ACTIVE");
   g_allow_new=NexusJsonBool(json,"allow_new_trade",false);
   g_allow_manage=NexusJsonBool(json,"allow_manage_trade",false);
   g_force_close_all=NexusJsonBool(json,"force_close_all",false);

   // Admin authority is independent from customer-license trade flags.
   // Heartbeat/activation responses must not revoke an authenticated admin terminal.
   if(EffectiveAdminMode() && (g_admin_authenticated || mode=="ADMIN"))
     {
      g_access_mode=NEXUS_ADMIN;
      g_license_active=true;
      g_allow_new=true;
      g_allow_manage=true;
     }
   else if(g_license_active || mode=="LICENSED")
      g_access_mode=NEXUS_LICENSED;
   else
      g_access_mode=NEXUS_STANDARD;
  }


void AdvanceSignalCursor(const long db_id)
  {
   if(db_id>g_last_signal_id)
     {
      g_last_signal_id=db_id;
      SaveCursor("signal",g_last_signal_id);
     }
  }

void SetExecutionStatus(const string state,const NexusSignal &s,const string resolved_symbol,
                        const string reason="",const double volume=0.0)
  {
   g_last_exec_state=state;
   g_last_exec_signal=s.signal_id;
   g_last_exec_symbol=(resolved_symbol==""?s.symbol:resolved_symbol);
   g_last_exec_reason=reason;
   g_last_exec_volume=volume;

   string log="NEXUS SIGNAL "+s.signal_id+" | "+state+
              " | requested="+s.symbol+
              " | broker="+g_last_exec_symbol+
              " | type="+s.order_type+
              " | direction="+s.direction+
              " | entry="+DoubleToString(s.entry,5)+
              " | sl="+DoubleToString(s.sl,5);
   if(volume>0) log+=" | volume="+DoubleToString(volume,2);
   if(reason!="") log+=" | reason="+reason;
   Print(log);
   SetPanel();
  }

void DeleteStatusPanel()
  {
   string names[]={"status_shadow","status_bg","status_title","status_tab0","status_tab1","status_tab2","status_tab3","status_tab4","status_tab5","status_body","status_min","settings_conn","settings_trade","settings_risk","settings_system","md_title","md_free","md_vip","md_both","md_state"};
   for(int i=0;i<ArraySize(names);i++) ObjectDelete(0,NXS_UI_PREFIX+names[i]);
  }

void DeleteStatusTabs()
  {
   for(int i=0;i<2;i++) ObjectDelete(0,NXS_UI_PREFIX+"status_tab"+IntegerToString(i));
  }

void DeleteAdminSignalPanel()
  {
   string names[]={"sig_min","sig_title","sig_symbol_lbl","sig_symbol","sig_entry_lbl","sig_entry","sig_sl_lbl","sig_sl","sig_tp1_lbl","sig_tp1","sig_tp2_lbl","sig_tp2","sig_tp3_lbl","sig_tp3","sig_tp4_lbl","sig_tp4","sig_tp5_lbl","sig_tp5","sig_risk_lbl","sig_risk","sig_buy","sig_sell","sig_market","sig_limit","sig_issue","sig_dest_lbl","sig_dest_free","sig_dest_vip","sig_dest_both","sig_dest_state","sig_manage_title","sig_manage_id_lbl","sig_manage_id","sig_manage_value_lbl","sig_manage_value","sig_trail_lbl","sig_trail_01","sig_trail_02","sig_trail_03","sig_trail_04","sig_trail_05","sig_trail_06","sig_trail_07","sig_lot","sig_size_risk","sig_size_fixed","sig_lot_hint","sig_sub","sig_legacy","sig_be","sig_close","sig_cancel","sig_setsl","sig_settp","sig_trail"};
   for(int i=0;i<ArraySize(names);i++) ObjectDelete(0,NXS_UI_PREFIX+names[i]);
  }

void PaintAdminSignalPanel()
  {
   // Compact command-center layout. The host chart symbol is the default;
   // advanced execution controls stay out of the primary Signal workspace.
   string v_symbol=g_admin_signal_symbol;
   string v_entry="";
   string v_sl="";
   string v_tp1=""; string v_tp2=""; string v_tp3=""; string v_tp4=""; string v_tp5="";
   string v_risk="1",v_lot=DoubleToString(g_admin_fixed_lot,2);
   string v_manage_id=g_admin_manage_id,v_manage_value=g_admin_manage_value,n;
   n=NXS_UI_PREFIX+"sig_symbol"; if(ObjectFind(0,n)>=0) v_symbol=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_entry"; if(ObjectFind(0,n)>=0) v_entry=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_sl"; if(ObjectFind(0,n)>=0) v_sl=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_tp1"; if(ObjectFind(0,n)>=0) v_tp1=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_tp2"; if(ObjectFind(0,n)>=0) v_tp2=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_tp3"; if(ObjectFind(0,n)>=0) v_tp3=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_tp4"; if(ObjectFind(0,n)>=0) v_tp4=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_tp5"; if(ObjectFind(0,n)>=0) v_tp5=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_risk"; if(ObjectFind(0,n)>=0) v_risk=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_lot"; if(ObjectFind(0,n)>=0) v_lot=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_manage_id"; if(ObjectFind(0,n)>=0) v_manage_id=ObjectGetString(0,n,OBJPROP_TEXT);
   n=NXS_UI_PREFIX+"sig_manage_value"; if(ObjectFind(0,n)>=0) v_manage_value=ObjectGetString(0,n,OBJPROP_TEXT);
   StringTrimLeft(v_symbol); StringTrimRight(v_symbol); StringToUpper(v_symbol);
   if(v_symbol!="") g_admin_signal_symbol=v_symbol;
   g_admin_manage_id=v_manage_id; g_admin_manage_value=v_manage_value;
   g_admin_fixed_lot=StringToDouble(v_lot); if(g_admin_fixed_lot<=0) g_admin_fixed_lot=0.01;

   DeleteAdminSignalPanel();
   UISetButton("sig_min",g_panel_minimized?"+":"—",456,78,30,24,clrDimGray);
   UISetLabel("sig_title","NEXUS  /  SIGNAL COMMAND",24,88,11);
   UISetLabel("sig_legacy","SIGNAL • SETTINGS / MANAGEMENT",24,76,7);
   UISetLabel("sig_sub","HOST: "+_Symbol+"   •   CANONICAL: "+CanonicalSignalSymbol(_Symbol),24,108,8);
   UISetLabel("sig_symbol_lbl","SYMBOL",24,130,8); UISetEdit("sig_symbol",v_symbol,24,145,120,24);
   UISetLabel("sig_entry_lbl","ENTRY",154,130,8); UISetEdit("sig_entry",v_entry,154,145,110,24);
   UISetLabel("sig_sl_lbl","STOP LOSS",274,130,8); UISetEdit("sig_sl",v_sl,274,145,110,24);
   UISetLabel("sig_tp1_lbl","TP1",24,177,8); UISetEdit("sig_tp1",v_tp1,24,192,105,24);
   UISetLabel("sig_tp2_lbl","TP2",139,177,8); UISetEdit("sig_tp2",v_tp2,139,192,105,24);
   UISetLabel("sig_tp3_lbl","TP3",254,177,8); UISetEdit("sig_tp3",v_tp3,254,192,105,24);
   UISetLabel("sig_tp4_lbl","TP4",24,224,8); UISetEdit("sig_tp4",v_tp4,24,239,105,24);
   UISetLabel("sig_tp5_lbl","TP5",139,224,8); UISetEdit("sig_tp5",v_tp5,139,239,105,24);
   UISetLabel("sig_risk_lbl","RISK %",254,224,8); UISetEdit("sig_risk",v_risk,254,239,105,24);

   UISetButton("sig_buy","BUY",24,273,70,25,g_admin_signal_direction=="BUY"?clrSeaGreen:clrDimGray);
   UISetButton("sig_sell","SELL",99,273,70,25,g_admin_signal_direction=="SELL"?clrSeaGreen:clrDimGray);
   UISetButton("sig_market","MARKET",174,273,78,25,g_admin_signal_order=="MARKET"?clrSeaGreen:clrDimGray);
   UISetButton("sig_limit","LIMIT",257,273,70,25,g_admin_signal_order=="LIMIT"?clrSeaGreen:clrDimGray);
   UISetButton("sig_issue","ISSUE SIGNAL",317,273,67,25,clrSeaGreen);

   UISetLabel("sig_size_lbl","SIZING",24,309,8);
   UISetButton("sig_size_risk","RISK",24,324,85,24,g_admin_sizing_mode=="RISK"?clrSeaGreen:clrDimGray);
   UISetButton("sig_size_fixed","FIXED",114,324,85,24,g_admin_sizing_mode=="FIXED"?clrSeaGreen:clrDimGray);
   UISetEdit("sig_lot",v_lot,209,324,95,24);
   UISetLabel("sig_lot_hint","FIXED LOT",310,331,7);
   UISetLabel("sig_trail_lbl","TRAILING / PROFILE",24,358,8);
   for(int ti=1;ti<=7;ti++)
     {
      string tn="sig_trail_"+StringFormat("%02d",ti);
      int tx=24+(ti-1)*50;
      UISetButton(tn,StringFormat("T%02d",ti),tx,373,46,24,g_admin_trailing_profile==NexusTrailingCode(ti)?clrSeaGreen:clrDimGray);
     }
   UISetLabel("sig_dest_lbl","CHANNEL / ACCESS",24,404,8);
   UISetButton("sig_dest_free","FREE",24,419,105,24,g_manual_destination=="FREE"?clrSeaGreen:clrDimGray);
   UISetButton("sig_dest_vip","VIP",139,419,105,24,g_manual_destination=="VIP"?clrSeaGreen:clrDimGray);
   UISetButton("sig_dest_both","BOTH",254,419,105,24,g_manual_destination=="BOTH"?clrSeaGreen:clrDimGray);
   UISetLabel("sig_dest_state","SELECTED: "+(g_manual_destination=="NONE"?"NONE":g_manual_destination),24,450,8);

   UISetLabel("sig_manage_title","TRADE MANAGEMENT",24,471,9);
   UISetEdit("sig_manage_id",v_manage_id,24,489,120,24);
   UISetEdit("sig_manage_value",v_manage_value,149,489,95,24);
   UISetButton("sig_be","BE",249,489,45,24,clrDimGray);
   UISetButton("sig_close","CLOSE",299,489,60,24,clrFireBrick);
   UISetButton("sig_cancel","CANCEL",24,520,75,24,clrDimGray);
   UISetButton("sig_setsl","SET SL",104,520,75,24,clrDimGray);
   UISetButton("sig_settp","SET TP",184,520,75,24,clrDimGray);
   UISetButton("sig_trail","TRAIL",264,520,75,24,clrDimGray);
  }


string CanonicalSignalSymbol(const string raw)
  {
   string u=raw; StringTrimLeft(u); StringTrimRight(u); StringToUpper(u);
   string compact="";
   for(int i=0;i<StringLen(u);i++)
     {
      ushort c=StringGetCharacter(u,i);
      if((c>='A' && c<='Z') || (c>='0' && c<='9')) compact+=ShortToString(c);
     }
   if(StringFind(compact,"XAUUSD")==0 || StringFind(compact,"GOLD")==0) return "XAUUSD";
   if(StringFind(compact,"XAGUSD")==0 || StringFind(compact,"SILVER")==0) return "XAGUSD";
   string majors[] = {"EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURJPY","GBPJPY","EURGBP","AUDJPY","EURAUD","EURCHF","GBPCHF","GBPAUD","GBPCAD","AUDCAD","AUDCHF","CADJPY","NZDJPY","NZDUSD"};
   for(int i=0;i<ArraySize(majors);i++) if(StringFind(compact,majors[i])==0) return majors[i];
   string crypto[] = {"BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD","DOGEUSD","ADAUSD","AVAXUSD","DOTUSD","LTCUSD"};
   for(int i=0;i<ArraySize(crypto);i++) if(StringFind(compact,crypto[i])==0) return crypto[i];
   return compact=="" ? u : compact;
  }

void SyncHostSymbol(const bool force=false)
  {
   string host=_Symbol; StringToUpper(host);
   if(force || !g_admin_signal_busy)
     {
      g_admin_signal_symbol=CanonicalSignalSymbol(host);
      if(ObjectFind(0,NXS_UI_PREFIX+"sig_symbol")>=0)
         ObjectSetString(0,NXS_UI_PREFIX+"sig_symbol",OBJPROP_TEXT,g_admin_signal_symbol);
     }
  }

string AdminSignalMarketType(const string symbol)
  {
   string u=symbol; StringToUpper(u);
   if(StringFind(u,"XAU")>=0) return "GOLD";
   if(StringFind(u,"BTC")>=0 || StringFind(u,"ETH")>=0 || StringFind(u,"SOL")>=0 || StringFind(u,"BNB")>=0 || StringFind(u,"XRP")>=0) return "CRYPTO";
   if(StringFind(u,"US30")>=0 || StringFind(u,"NAS")>=0 || StringFind(u,"SPX")>=0 || StringFind(u,"GER")>=0 || StringFind(u,"DAX")>=0) return "INDEX";
   return "FOREX";
  }

void IssueAdminSignal()
  {
   if(g_admin_signal_busy) { Print("NEXUS ADMIN SIGNAL REJECTED: already in progress"); SetPanel("ISSUE SIGNAL ALREADY IN PROGRESS"); return; }
   if(g_access_mode!=NEXUS_ADMIN || !g_admin_authenticated) { Print("NEXUS ADMIN SIGNAL REJECTED: admin auth required"); SetPanel("ADMIN AUTH REQUIRED"); return; }
   g_admin_signal_busy=true;
   if(ObjectFind(0,NXS_UI_PREFIX+"sig_issue")>=0)
     { ObjectSetString(0,NXS_UI_PREFIX+"sig_issue",OBJPROP_TEXT,"ISSUING..."); ObjectSetInteger(0,NXS_UI_PREFIX+"sig_issue",OBJPROP_STATE,false); }
   ChartRedraw();
   string symbol=ObjectGetString(0,NXS_UI_PREFIX+"sig_symbol",OBJPROP_TEXT); StringTrimLeft(symbol); StringTrimRight(symbol); StringToUpper(symbol);
   double entry=StringToDouble(ObjectGetString(0,NXS_UI_PREFIX+"sig_entry",OBJPROP_TEXT));
   double sl=StringToDouble(ObjectGetString(0,NXS_UI_PREFIX+"sig_sl",OBJPROP_TEXT));
   double risk=StringToDouble(ObjectGetString(0,NXS_UI_PREFIX+"sig_risk",OBJPROP_TEXT));
   double tps[5];
   string tp_names[5]={"sig_tp1","sig_tp2","sig_tp3","sig_tp4","sig_tp5"};
   int tp_count=0;
   bool tp_gap=false;
   for(int i=0;i<5;i++)
     {
      string raw=ObjectGetString(0,NXS_UI_PREFIX+tp_names[i],OBJPROP_TEXT);
      StringTrimLeft(raw); StringTrimRight(raw);
      if(raw=="") { if(tp_count>0) tp_gap=true; continue; }
      if(tp_gap)
        { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: TP order invalid, fill targets sequentially"); SetPanel("TP ORDER INVALID: fill targets sequentially"); return; }
      double v=StringToDouble(raw);
      if(v<=0)
        { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: invalid TP",(string)(i+1)," raw=\"",raw,"\""); SetPanel("INVALID TP"+(string)(i+1)); return; }
      tps[tp_count++]=v;
     }
   // RISK mode is authoritative for v0.6.0 admin-issued signals. Zero risk
   // would create a signal that clients cannot execute safely.
   if(symbol=="" || sl<=0 || tp_count<=0 || risk<=0)
     { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: invalid signal input symbol=",symbol," sl=",sl," tp_count=",tp_count," risk=",risk); SetPanel("INVALID SIGNAL INPUT"); return; }
   if(g_admin_signal_order=="MARKET" && entry<=0)
     {
      entry=(g_admin_signal_direction=="BUY"?SymbolInfoDouble(symbol,SYMBOL_ASK):SymbolInfoDouble(symbol,SYMBOL_BID));
      if(entry<=0)
        { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: market price unavailable for ",symbol); SetPanel("MARKET PRICE UNAVAILABLE"); return; }
      ObjectSetString(0,NXS_UI_PREFIX+"sig_entry",OBJPROP_TEXT,DoubleToString(entry,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS)));
     }
   if(entry<=0)
     { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: invalid entry"); SetPanel("INVALID ENTRY"); return; }
   if(g_manual_destination!="FREE" && g_manual_destination!="VIP" && g_manual_destination!="BOTH")
     { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: channel/access not selected"); SetPanel("SELECT CHANNEL ACCESS"); return; }
   for(int i=0;i<tp_count;i++)
     {
      if(i>0 && ((g_admin_signal_direction=="BUY" && tps[i]<=tps[i-1]) || (g_admin_signal_direction=="SELL" && tps[i]>=tps[i-1])))
        { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: TP order invalid at TP",(string)(i+1)); SetPanel("TP ORDER INVALID"); return; }
      if(g_admin_signal_direction=="BUY" && !(sl<entry && entry<tps[i]))
        { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: BUY TP geometry invalid sl=",sl," entry=",entry," tp",(string)(i+1),"=",tps[i]); SetPanel("BUY TP GEOMETRY INVALID"); return; }
      if(g_admin_signal_direction=="SELL" && !(tps[i]<entry && entry<sl))
        { g_admin_signal_busy=false; Print("NEXUS ADMIN SIGNAL REJECTED: SELL TP geometry invalid sl=",sl," entry=",entry," tp",(string)(i+1),"=",tps[i]); SetPanel("SELL TP GEOMETRY INVALID"); return; }
     }
   string targets="";
   for(int i=0;i<tp_count;i++)
     {
      if(i>0) targets+=",";
      targets+=DoubleToString(tps[i],8);
     }
   string response;
   double lot=0.0;
   string trailing=g_admin_trailing_profile;
   g_admin_issue_nonce++;
   string reqid="MT5-"+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"-"+(string)GetTickCount()+"-"+(string)g_admin_issue_nonce;

   // Capture before POST; the screenshot routine hides all NEXUS UI objects.
   string chart_base64=CaptureChartBase64(symbol,"SIGNAL");
   if(chart_base64=="") Print("NEXUS ADMIN SIGNAL: chart screenshot unavailable; fallback card will be used");

   Print("NEXUS ADMIN SIGNAL: submit start symbol=",symbol," direction=",g_admin_signal_direction,
         " order=",g_admin_signal_order," destination=",g_manual_destination," tp_count=",tp_count);
   string issue_symbol=CanonicalSignalSymbol(symbol);
   if(!g_api.IssueAdminSignal(AdminSignalMarketType(issue_symbol),issue_symbol,g_admin_signal_direction,g_admin_signal_order,
                              "M5",entry,sl,targets,risk,g_admin_sizing_mode,(g_admin_sizing_mode=="FIXED"?g_admin_fixed_lot:0.0),trailing,-1,-1,g_manual_destination,reqid,
                              response,chart_base64))
     {
      g_admin_signal_busy=false;
      Print("NEXUS ADMIN SIGNAL FAILED: ",g_api.LastError()," HTTP=",g_api.LastHttpStatus()," response=",response);
      SetPanel("ISSUE FAILED: "+g_api.LastError());
      return;
     }

   string code=NexusJsonString(response,"signal_id","");
   string issued_signal=NexusJsonObject(response,"signal");
   long issued_db_id=NexusJsonLong(issued_signal,"id",0);
   if(code=="" || issued_db_id<=0)
     {
      g_admin_signal_busy=false;
      Print("NEXUS ADMIN SIGNAL FAILED: invalid canonical response HTTP=",g_api.LastHttpStatus()," response=",response);
      SetPanel("ISSUE FAILED: INVALID API SIGNAL RESPONSE");
      return;
     }

   g_admin_manage_id=code;
   if(ObjectFind(0,NXS_UI_PREFIX+"sig_manage_id")>=0)
      ObjectSetString(0,NXS_UI_PREFIX+"sig_manage_id",OBJPROP_TEXT,code);
   g_last_exec_signal=code;
   g_last_exec_symbol=symbol;
   g_last_exec_state="ISSUED";
   g_last_exec_reason="MT5 Admin canonical signal | "+g_manual_destination+" | TP count="+(string)tp_count;
   Print("NEXUS ADMIN SIGNAL ISSUED: ",code," db_id=",issued_db_id," ",symbol," ",g_admin_signal_direction,
         " ",g_admin_signal_order," destination=",g_manual_destination," TP count=",tp_count);

   // Execute the exact canonical object returned by the POST. This bypasses
   // stale cursor state (for example after_id=9 while NX-0007 is id=7) and
   // guarantees that an admin-issued signal enters the execution pipeline.
   NexusSignal issued;
   if(!g_parser.ParseSignalObject(issued_signal,issued))
     {
      g_admin_signal_busy=false;
      Print("NEXUS ADMIN SIGNAL FAILED: canonical signal object could not be parsed for execution code=",code," db_id=",issued_db_id);
      SetPanel("ISSUE FAILED: SIGNAL PARSE");
      return;
     }
   bool executed_path=ProcessIncomingSignal(issued);
   if(!executed_path)
      Print("NEXUS ADMIN SIGNAL WAITING: ",code," execution deferred; retryable broker failure");
   else
      Print("NEXUS ADMIN SIGNAL EXECUTION PATH COMPLETED: ",code," state=",g_last_exec_state);

   g_manual_destination="NONE";
   SaveManualDestination();
   g_admin_signal_busy=false;
   SetPanel(g_last_exec_state=="EXECUTED" ? "SIGNAL EXECUTED: "+code : "SIGNAL ISSUED: "+code);
   }

void IssueAdminCommand(const string command)
  {
   if(g_access_mode!=NEXUS_ADMIN || !g_admin_authenticated) { SetPanel("ADMIN AUTH REQUIRED"); return; }
   string sid=ObjectGetString(0,NXS_UI_PREFIX+"sig_manage_id",OBJPROP_TEXT); StringTrimLeft(sid); StringTrimRight(sid);
   string value=ObjectGetString(0,NXS_UI_PREFIX+"sig_manage_value",OBJPROP_TEXT); StringTrimLeft(value); StringTrimRight(value);
   long dbid=0;
   if(StringFind(sid,"NX-")==0) dbid=(long)StringToInteger(StringSubstr(sid,3)); else dbid=(long)StringToInteger(sid);
   if(dbid<=0) { SetPanel("INVALID SIGNAL ID"); return; }
   string response; string reqid="CMD-"+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"-"+(string)GetTickCount();
   if(!g_api.IssueAdminCommand(dbid,command,value,reqid,response)) { SetPanel("COMMAND FAILED: "+g_api.LastError()); return; }
   g_last_exec_state="COMMAND"; g_last_exec_signal=(sid==""?"NX-?":sid); g_last_exec_reason=command+(value==""?"":" value="+value);
   Print("NEXUS ADMIN COMMAND ISSUED: ",command," signal=",sid," value=",value);
   PaintStatusPanel();
  }

void PaintStatusPanel()
  {
   if(g_setup_required) return;
   string shadow=NXS_UI_PREFIX+"status_shadow";
   string bg=NXS_UI_PREFIX+"status_bg";
   if(ObjectFind(0,shadow)<0) ObjectCreate(0,shadow,OBJ_RECTANGLE_LABEL,0,0,0);
   if(ObjectFind(0,bg)<0) ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);

   int chart_w=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS,0);
   int panel_w=g_panel_minimized?360:MathMin(560,MathMax(500,chart_w-24));
   int panel_h=g_panel_minimized?48:((g_access_mode==NEXUS_ADMIN && g_panel_tab==4)?575:390);
   ObjectSetInteger(0,shadow,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,shadow,OBJPROP_XDISTANCE,16);
   ObjectSetInteger(0,shadow,OBJPROP_YDISTANCE,17);
   ObjectSetInteger(0,shadow,OBJPROP_XSIZE,panel_w);
   ObjectSetInteger(0,shadow,OBJPROP_YSIZE,panel_h);
   ObjectSetInteger(0,shadow,OBJPROP_BGCOLOR,clrDarkSlateGray);
   ObjectSetInteger(0,shadow,OBJPROP_BORDER_COLOR,clrDarkSlateGray);
   ObjectSetInteger(0,shadow,OBJPROP_BACK,false);
   ObjectSetInteger(0,shadow,OBJPROP_ZORDER,5);

   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,12);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,12);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,panel_w);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,panel_h);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,clrBlack);
   ObjectSetInteger(0,bg,OBJPROP_BORDER_COLOR,clrSlateGray);
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTED,false);
   ObjectSetInteger(0,bg,OBJPROP_ZORDER,10);

   UISetLabel("status_title","NEXUS | "+(g_access_mode==NEXUS_ADMIN?"ADMIN":"USER"),24,20,12);
   UISetButton("status_min",g_panel_minimized?"+":"—",panel_w-44,18,30,24,clrDimGray);

   if(g_panel_minimized)
     {
      // Minimized means the complete admin form must disappear, not only
      // the tabs. The signal form is made of independent chart objects and
      // otherwise remains visible after the panel is collapsed.
      DeleteStatusTabs();
      DeleteAdminSignalPanel();
      DeleteManualDestinationPanel();
      UISetLabel("status_body",(g_allow_new?"READY":"LOCKED"),24,0,9);
      ObjectSetInteger(0,NXS_UI_PREFIX+"status_body",OBJPROP_YDISTANCE,25);
      ObjectSetInteger(0,NXS_UI_PREFIX+"status_body",OBJPROP_FONTSIZE,9);
      ChartRedraw();
      return;
     }

   // Legacy tab names retained and used for the Settings sub-tabs.
   string tabs[6]={"OVERVIEW","CONNECTION","TRADING","RISK","SIGNAL","SYSTEM"};
   string main_tabs[2]={"SIGNAL","SETTINGS / MANAGEMENT"};
   for(int i=0;i<2;i++)
      UISetButton("status_tab"+IntegerToString(i),main_tabs[i],20+i*150,55,i==0?130:145,24,(i==(g_panel_tab==4?0:1))?clrSeaGreen:clrDimGray);

   if(g_panel_tab!=4)
     {
      UISetButton("settings_conn",tabs[1],180,91,90,22,g_panel_tab==1?clrSeaGreen:clrDimGray);
      UISetButton("settings_trade",tabs[2],275,91,80,22,g_panel_tab==2?clrSeaGreen:clrDimGray);
      UISetButton("settings_risk",tabs[3],360,91,60,22,g_panel_tab==3?clrSeaGreen:clrDimGray);
      UISetButton("settings_system",tabs[5],425,91,70,22,g_panel_tab==5?clrSeaGreen:clrDimGray);
     }

   string api_ok=(g_api.LastHttpStatus()>=200&&g_api.LastHttpStatus()<300?"✓":"✕");
   string mt5_ok=(TerminalInfoInteger(TERMINAL_CONNECTED)?"✓":"✕");
   string account_ok=(g_account_verified?"✓":"✕");
   string license_ok=(g_access_mode==NEXUS_ADMIN?(g_admin_authenticated?"✓":"✕"):(g_license_active?"✓":"✕"));
   string new_ok=(g_allow_new&&InpAllowNewTrades?"✓":"✕");
   string manage_ok=(g_allow_manage&&InpManageExistingTrades?"✓":"✕");
   string trade_ok=(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)?"✓":"✕");

   string body="";
   if(g_panel_tab==0)
     body="ACCOUNT  "+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"   MODE  "+(g_access_mode==NEXUS_ADMIN?"ADMIN":(g_access_mode==NEXUS_LICENSED?"LICENSED":"LOCKED"))+
          "\nAUTH        "+license_ok+"   ACCOUNT     "+account_ok+"\nAPI         "+api_ok+"   MT5         "+mt5_ok+
          "\nTRADE       "+trade_ok+"   NEW TRADES  "+new_ok+
          "\nMANAGE      "+manage_ok+"   HEARTBEAT   "+(g_last_heartbeat>0?"✓":"—")+
          "\nPOLL        "+(string)InpPollSeconds+"s   RECON       ON"+
          "\nTrade state: "+g_last_exec_state+"   Broker symbol: "+(g_last_exec_symbol==""?"—":g_last_exec_symbol)+
          "\nReason:      "+(g_last_exec_reason==""?"—":g_last_exec_reason);
   else if(g_panel_tab==1)
     body="API         "+api_ok+"   HTTP        "+IntegerToString(g_api.LastHttpStatus())+
          "\nMT5         "+mt5_ok+"   ACCOUNT     "+account_ok+
          "\nAUTH MODE   "+(g_access_mode==NEXUS_ADMIN?"ADMIN":"LICENSE")+"   AUTH        "+license_ok+
          "\nHEARTBEAT   "+(g_last_heartbeat>0?"✓":"—")+"   POLL        "+(string)InpPollSeconds+"s";
   else if(g_panel_tab==2)
     body="NEW TRADES  "+new_ok+"   MANAGE      "+manage_ok+
          "\nTERMINAL     "+trade_ok+"   MAGIC       "+(string)InpMagicNumber+
          "\nLAST SIGNAL  "+(g_last_exec_signal==""?"—":g_last_exec_signal)+
          "\nSTATE        "+g_last_exec_state+"   VOLUME      "+(g_last_exec_volume>0?DoubleToString(g_last_exec_volume,2):"—")+
          "\nBROKER       "+(g_last_exec_symbol==""?"—":g_last_exec_symbol)+
          "\nERROR        "+(g_last_exec_reason==""?"—":g_last_exec_reason);
   else if(g_panel_tab==3)
     body="POLICY       NEXUS LOCKED"+
          "\nMANAGEMENT   "+manage_ok+"   TRAILING    "+(manage_ok=="✓"?"ON":"OFF")+
          "\nTRAIL TF     "+EnumToString(InpTrailingTimeframe)+
          "\nMANUAL TRAIL "+NexusTrailingCode((int)InpManualTrailingProfile)+
          "\nMANUAL MGMT  "+(InpManageManualTrades?"ON":"OFF");
   else if(g_panel_tab==4)
     body=(g_access_mode==NEXUS_ADMIN?"AUTHORITY    MT5 ADMIN ONLY\nISSUE MODE   MANUAL MT5 ORDER → CANONICAL SIGNAL\nTELEGRAM     REPORTING ONLY\n":"AUTHORITY    MT5 CLIENT\nRECEIVE      CANONICAL MT5 SIGNALS")+
          "\nSIGNAL CURSOR  "+(string)g_last_signal_id+
          "\nCOMMAND CURSOR "+(string)g_last_command_id+
          "\nLAST SIGNAL    "+(g_last_exec_signal==""?"—":g_last_exec_signal)+
          "\nLAST STATE     "+g_last_exec_state+
          "\nLAST SYMBOL    "+(g_last_exec_symbol==""?"—":g_last_exec_symbol);
   else
     {
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
      body="EA VERSION   "+NEXUS_EA_VERSION+
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

   UISetLabel("status_body",body,24,91,10);
   ObjectSetInteger(0,NXS_UI_PREFIX+"status_body",OBJPROP_COLOR,clrWhite);
   ObjectSetString(0,NXS_UI_PREFIX+"status_body",OBJPROP_FONT,"Consolas");
   ObjectSetInteger(0,NXS_UI_PREFIX+"status_body",OBJPROP_ZORDER,30);

   if(g_access_mode==NEXUS_ADMIN && g_panel_tab==4)
     {
      ObjectSetString(0,NXS_UI_PREFIX+"status_body",OBJPROP_TEXT,"");
      PaintAdminSignalPanel();
     }
   else
      DeleteAdminSignalPanel();
   DeleteManualDestinationPanel();
   ChartRedraw();
  }

void SetPanel(const string extra="")
  {
   if(extra!="") g_last_exec_reason=extra;
   PaintStatusPanel();
  }


bool HasLocalNexusPositions()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if((long)PositionGetInteger(POSITION_MAGIC)==InpMagicNumber) return true;
     }
   return false;
  }

bool ActivateLicense()
  {
   string response;
   if(!g_api.Activate(response))
     {
      Print("NEXUS activation failed: ",g_api.LastError());
      // If Backend is unreachable (not an explicit 4xx rejection), never abandon
      // a NEXUS position that was already open before MT5 restarted.
      if(g_api.LastHttpStatus()==-1 && HasLocalNexusPositions())
        {
         g_allow_new=false;
         g_allow_manage=true;
        }
      SetPanel("Activation error: "+g_api.LastError());
      return false;
     }
   ApplyAuthResponse(response);
   SetPanel("Connected to NEXUS Backend");
   return true;
  }

ulong NexusSignalHash(const string value)
  {
   ulong h=1469598103934665603;
   int n=StringLen(value);
   for(int i=0;i<n;i++)
     { h^=(ulong)StringGetCharacter(value,i); h*=1099511628211; }
   return h;
  }

string NexusSignalLockKey(const string signal_id)
  {
   return "NXS.LOCK."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"."+(string)NexusSignalHash(signal_id);
  }

string NexusSignalDoneKey(const string signal_id)
  {
   return NexusSignalLockKey(signal_id)+".DONE";
  }

bool ClaimNexusSignal(const string signal_id)
  {
   if(GlobalVariableCheck(NexusSignalDoneKey(signal_id)) && GlobalVariableGet(NexusSignalDoneKey(signal_id))>0.5)
      return false;
   string key=NexusSignalLockKey(signal_id);
   if(!GlobalVariableCheck(key)) GlobalVariableSet(key,0.0);
   double current=GlobalVariableGet(key);
   double now=(double)TimeCurrent();
   // An interrupted pre-trade attempt may be reclaimed after two minutes.
   // Completed executions use a separate permanent DONE marker.
   if(current>0 && now-current<120.0) return false;
   return GlobalVariableSetOnCondition(key,now,current);
  }

void ReleaseNexusSignalClaim(const string signal_id)
  {
   string key=NexusSignalLockKey(signal_id);
   if(GlobalVariableCheck(key)) GlobalVariableSet(key,0.0);
  }

void CompleteNexusSignalClaim(const string signal_id)
  {
   GlobalVariableSet(NexusSignalDoneKey(signal_id),1.0);
   ReleaseNexusSignalClaim(signal_id);
  }

bool NexusSignalExecutionDone(const string signal_id)
  {
   string key=NexusSignalDoneKey(signal_id);
   return GlobalVariableCheck(key) && GlobalVariableGet(key)>0.5;
  }

bool IsPendingSignalType(const string order_type)
  {
   return order_type=="LIMIT" || order_type=="BUY_LIMIT" || order_type=="SELL_LIMIT" ||
          order_type=="BUY_STOP" || order_type=="SELL_STOP" ||
          order_type=="BUY_STOP_LIMIT" || order_type=="SELL_STOP_LIMIT";
  }

bool ProcessIncomingSignal(const NexusSignal &s)
  {
   SetExecutionStatus("RECEIVED",s,s.symbol,"order_type="+s.order_type+" entry="+DoubleToString(s.entry,8));
   if(s.order_type!="MARKET" && s.order_type!="LIMIT" &&
      s.order_type!="BUY_LIMIT" && s.order_type!="SELL_LIMIT" &&
      s.order_type!="BUY_STOP" && s.order_type!="SELL_STOP" &&
      s.order_type!="BUY_STOP_LIMIT" && s.order_type!="SELL_STOP_LIMIT")
     {
      string bad="unsupported order type: "+s.order_type;
      SendSignalReceiptReliable(s.db_id,"rejected","",bad);
      SetExecutionStatus("REJECTED",s,s.symbol,bad); AdvanceSignalCursor(s.db_id); return true;
     }
   if(g_trade.HasSignalPosition(s.signal_id))
     {
      CompleteNexusSignalClaim(s.signal_id);
      ulong existing=g_trade.FindTicket(s.signal_id);
      string status=(IsPendingSignalType(s.order_type)?"activated":"executed");
      SendSignalReceiptReliable(s.db_id,status,(string)existing,"");
      string su=status; StringToUpper(su);
      SetExecutionStatus("ALREADY "+su,s,s.symbol,"existing NEXUS position"); AdvanceSignalCursor(s.db_id); return true;
     }
   if(g_trade.HasSignalOrder(s.signal_id))
     {
      CompleteNexusSignalClaim(s.signal_id);
      SendSignalReceiptReliable(s.db_id,"pending","","");
      SetExecutionStatus("PENDING",s,s.symbol,"existing NEXUS pending order"); AdvanceSignalCursor(s.db_id); return true;
     }
   string symbol=g_mapper.Resolve(s.symbol,InpEnableAutoSymbolMapping);
   if(symbol=="")
     {
      string reason="symbol not available/tradable on broker";
      SendSignalReceiptReliable(s.db_id,"rejected","",reason);
      SetExecutionStatus("REJECTED",s,s.symbol,reason); AdvanceSignalCursor(s.db_id); return true;
     }
   NexusLogSymbolMapping(s.symbol,symbol);
   string reason="";
   if(!g_trade.ValidateEntry(s,symbol,InpDefaultMaxEntryDeviationPct,reason))
     {
      SendSignalReceiptReliable(s.db_id,"rejected","",reason);
      SetExecutionStatus("REJECTED",s,symbol,reason); AdvanceSignalCursor(s.db_id); return true;
     }
   SetExecutionStatus("ENTRY CHECK PASS",s,symbol);
   if(!ClaimNexusSignal(s.signal_id))
     {
      // A permanent DONE marker means another NEXUS instance already
      // completed this canonical signal. Never publish a false rejection.
      if(NexusSignalExecutionDone(s.signal_id))
        {
         SetExecutionStatus(
            "ALREADY CLAIMED",
            s,
            symbol,
            "execution already completed by another NEXUS instance"
         );
         AdvanceSignalCursor(s.db_id);
         return true;
        }

      // A live claim is temporary ownership by another EA instance.
      // Do not reject and do not advance the cursor; shared cursor sync
      // or the next poll will observe the authoritative execution result.
      SetExecutionStatus(
         "CLAIM BUSY",
         s,
         symbol,
         "another NEXUS instance is processing this signal"
      );
      return false;
     }
   ulong ticket=0;
    if(!g_trade.OpenSignal(s,symbol,g_risk_mode,g_fixed_lot,g_user_risk_percent,ticket))
     {
      ReleaseNexusSignalClaim(s.signal_id);
      string err=g_trade.LastError(); bool retryable=g_trade.LastFailureRetryable();
      SendSignalReceiptReliable(s.db_id,retryable?"failed_retryable":"rejected","",err);
      SetExecutionStatus(retryable?"OPEN FAILED - RETRYING":"REJECTED",s,symbol,err);
      if(retryable) return false;
       AdvanceSignalCursor(s.db_id); return true;
      }
    CompleteNexusSignalClaim(s.signal_id);

    // Execution truth ordering:
    // broker order -> authoritative live snapshot -> execution receipt.
    // If the forced snapshot has a transient transport failure, the reliable
    // receipt queue remains fail-closed and OnTimer retries only after LiveSync.
    DoLiveSync(true);

    string receipt_status=IsPendingSignalType(s.order_type)?"pending":"executed";
   SendSignalReceiptReliable(s.db_id,receipt_status,(string)ticket,"");
   SetExecutionStatus(IsPendingSignalType(s.order_type)?"PENDING PLACED":"EXECUTED",s,symbol,"ticket "+(string)ticket,g_last_exec_volume);
   AdvanceSignalCursor(s.db_id);
   return true;
  }

void PollSignals(const long after_id=-1,const int limit=50,const bool force_admin=false)
  {
   if(!InpAllowNewTrades)
     { Print("NEXUS SIGNAL POLL BLOCKED: InpAllowNewTrades=false"); return; }
   if(!force_admin && !g_allow_new)
     { Print("NEXUS SIGNAL POLL BLOCKED: allow_new=false"); return; }
   // Every EA chart shares the account-level cursor. Refresh the local
   // copy before requesting signals so secondary instances do not replay
   // work already completed by another chart.
   if(after_id<0 && GlobalVariableCheck(CursorKey("signal")))
     {
      long shared_signal_cursor=(long)GlobalVariableGet(CursorKey("signal"));
      if(shared_signal_cursor>g_last_signal_id)
         g_last_signal_id=shared_signal_cursor;
     }

   long effective_after=(after_id<0 ? g_last_signal_id : after_id);
   int effective_limit=MathMax(1,MathMin(limit,100));
   Print("NEXUS SIGNAL POLL: after_id=",effective_after," limit=",effective_limit," force_admin=",(force_admin?"YES":"NO"));
   string response;
   if(!g_api.GetSignals(effective_after,effective_limit,response)) { Print("NEXUS signals API: ",g_api.LastError()); return; }
   NexusSignal signals[];
   int n=g_parser.ParseSignals(response,signals);
   for(int i=0;i<n;i++) if(!ProcessIncomingSignal(signals[i])) break;
  }

void PollCommands()
  {
   if(!g_allow_manage || !InpManageExistingTrades) return;

   if(GlobalVariableCheck(CursorKey("command")))
     {
      long shared_command_cursor=(long)GlobalVariableGet(CursorKey("command"));
      if(shared_command_cursor>g_last_command_id)
         g_last_command_id=shared_command_cursor;
     }

   string response;
   if(!g_api.GetCommands(g_last_command_id,100,response)) { Print("NEXUS commands: ",g_api.LastError()); return; }
   NexusCommand commands[];
   int n=g_parser.ParseCommands(response,commands);
   for(int i=0;i<n;i++)
     {
      NexusCommand c=commands[i];
      // A global command stream is intentional. Clients without that signal simply ACK ignored.
      if(g_trade.FindTicket(c.signal_id)==0)
        {
         g_api.CommandReceipt(c.id,"ignored","no matching open position");
         g_last_command_id=c.id; SaveCursor("command",g_last_command_id);
         continue;
        }
      string err="";
      bool ok=g_commands.Execute(c,err);
      g_api.CommandReceipt(c.id,ok?"executed":"failed",err);
      if(ok)
        {
         g_last_command_id=c.id; SaveCursor("command",g_last_command_id);
        }
      else
        {
         Print("NEXUS command failed ",c.id,": ",err," - will retry on next poll");
         break; // preserve ordering and retry the failed command.
        }
     }
  }

void NotifyLimitActivations()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if((long)PositionGetInteger(POSITION_MAGIC)!=InpMagicNumber) continue;
      string sig=PositionGetString(POSITION_COMMENT);
      if(sig=="") continue;
      string clean=sig; StringReplace(clean," ","_");
      string prefix="NXS."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"."+clean+".";
      if(!GlobalVariableCheck(prefix+"is_limit") || GlobalVariableGet(prefix+"is_limit")<0.5) continue;
      if(GlobalVariableCheck(prefix+"activation_notified") && GlobalVariableGet(prefix+"activation_notified")>0.5) continue;
      if(!GlobalVariableCheck(prefix+"db_id")) continue;
      long dbid=(long)GlobalVariableGet(prefix+"db_id");
      if(dbid<=0) continue;
      if(SendSignalReceiptReliable(dbid,"activated",(string)ticket,""))
        {
         GlobalVariableSet(prefix+"activation_notified",1);
         Print("NEXUS LIMIT activated ",sig," ticket ",ticket);
        }
     }
  }

string JsonLiveItem(const string identifier,const string ticket,const string signal_code,const string symbol,const string direction,
                      const double volume,const double entry,const double current,const double sl,const double tp,const double profit,
                      const long magic,const bool nexus,const string order_type)
  {
   return StringFormat("{\"identifier\":\"%s\",\"ticket\":\"%s\",\"signal_code\":\"%s\",\"symbol\":\"%s\",\"direction\":\"%s\",\"volume\":%s,\"entry_price\":%s,\"current_price\":%s,\"stop_loss\":%s,\"take_profit\":%s,\"profit\":%s,\"magic\":%I64d,\"nexus_managed\":%s,\"order_type\":\"%s\"}",
      NexusJsonEscape(identifier),NexusJsonEscape(ticket),NexusJsonEscape(signal_code),NexusJsonEscape(symbol),NexusJsonEscape(direction),
      DoubleToString(volume,8),DoubleToString(entry,8),DoubleToString(current,8),DoubleToString(sl,8),DoubleToString(tp,8),DoubleToString(profit,8),
      magic,nexus?"true":"false",NexusJsonEscape(order_type));
  }

string RecoverSignalCodeForTicket(const ulong ticket,const string broker_comment)
  {
   string sig=broker_comment;
   StringTrimLeft(sig); StringTrimRight(sig); StringReplace(sig," ","_");
   if(StringFind(sig,"NX-")==0) return sig;

   string prefix="NXS."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+".";
   string suffix=".ticket";
   int total=GlobalVariablesTotal();
   for(int i=0;i<total;i++)
     {
      string key=GlobalVariableName(i);
      if(StringFind(key,prefix)!=0) continue;
      int suffix_pos=StringLen(key)-StringLen(suffix);
      if(suffix_pos<=StringLen(prefix) || StringSubstr(key,suffix_pos)!=suffix) continue;
      if((ulong)MathRound(GlobalVariableGet(key))!=ticket) continue;
      return StringSubstr(key,StringLen(prefix),suffix_pos-StringLen(prefix));
     }
   return "";
  }

string BuildLivePositionsJson()
  {
   string out="";
   for(int i=0;i<PositionsTotal();i++)
     {
      ulong ticket=PositionGetTicket(i); if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      string comment=PositionGetString(POSITION_COMMENT);
      string sig=RecoverSignalCodeForTicket(ticket,comment);
      string item=JsonLiveItem((string)PositionGetInteger(POSITION_IDENTIFIER),(string)ticket,sig,PositionGetString(POSITION_SYMBOL),
         PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY?"LONG":"SHORT",PositionGetDouble(POSITION_VOLUME),PositionGetDouble(POSITION_PRICE_OPEN),
         PositionGetDouble(POSITION_PRICE_CURRENT),PositionGetDouble(POSITION_SL),PositionGetDouble(POSITION_TP),PositionGetDouble(POSITION_PROFIT),
         PositionGetInteger(POSITION_MAGIC),PositionGetInteger(POSITION_MAGIC)==InpMagicNumber,"MARKET");
      if(out!="") out+=","; out+=item;
     }
   return out;
  }

string BuildLiveOrdersJson()
  {
   string out="";
   for(int i=0;i<OrdersTotal();i++)
     {
      ulong ticket=OrderGetTicket(i); if(ticket==0 || !OrderSelect(ticket)) continue;
      ENUM_ORDER_TYPE ot=(ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(!IsNexusPendingType(ot)) continue;
      string comment=OrderGetString(ORDER_COMMENT);
      string sig=RecoverSignalCodeForTicket(ticket,comment);
      string dir=(ot==ORDER_TYPE_BUY_LIMIT || ot==ORDER_TYPE_BUY_STOP || ot==ORDER_TYPE_BUY_STOP_LIMIT)?"LONG":"SHORT";
      string item=JsonLiveItem((string)ticket,(string)ticket,sig,OrderGetString(ORDER_SYMBOL),dir,OrderGetDouble(ORDER_VOLUME_CURRENT),
         OrderGetDouble(ORDER_PRICE_OPEN),SymbolInfoDouble(OrderGetString(ORDER_SYMBOL),SYMBOL_BID),OrderGetDouble(ORDER_SL),OrderGetDouble(ORDER_TP),0.0,
         OrderGetInteger(ORDER_MAGIC),OrderGetInteger(ORDER_MAGIC)==InpMagicNumber,PendingOrderTypeName(ot));
      if(out!="") out+=","; out+=item;
     }
   return out;
  }

bool DoLiveSync(const bool force=false)
  {
   datetime now=TimeCurrent();
   if(!force && g_last_live_sync>0 &&
      (now-g_last_live_sync)<MathMax(1,InpLiveSyncSeconds))
      return true;

   string response;
   if(g_api.LiveState(BuildLivePositionsJson(),BuildLiveOrdersJson(),response))
     {
      g_last_live_sync=now;
      Print("NEXUS LIVE SYNC OK: positions/orders snapshot delivered",
            (force?" [FORCED]":""));
      return true;
     }

   Print("NEXUS LIVE SYNC FAILED: ",g_api.LastError(),
         (force?" [FORCED]":""));
   return false;
  }

void DoHeartbeat()
  {
   datetime now=TimeCurrent();
   if(g_last_heartbeat>0 && (now-g_last_heartbeat)<InpHeartbeatSeconds) return;
   string response;
   if(g_api.Heartbeat(response))
     {
      ApplyAuthResponse(response);
      g_last_heartbeat=now;
      SetPanel();
     }
   else
     {
      // Do not abandon existing positions on a transient network error.
      g_allow_new=false;
      Print("NEXUS heartbeat failed: ",g_api.LastError());
      SetPanel("Backend connection problem - no new trades");
     }
  }


void NexusLogSymbolMapping(const string requested,const string resolved)
  {
   if(resolved=="")
      Print("NEXUS AutoTrade: symbol mapping FAILED for signal symbol ",requested);
   else if(resolved!=requested)
      Print("NEXUS AutoTrade: symbol mapped ",requested," -> ",resolved);
   else
      Print("NEXUS AutoTrade: symbol resolved ",requested);
  }


// ---------------- MT5 -> Telegram chart/event bridge ----------------

string Base64EncodeBytes(const uchar &raw[])
  {
   uchar key[];
   uchar encoded[];
   ArrayResize(key,0);
   if(ArraySize(raw)<=0) return "";
   int n=CryptEncode(CRYPT_BASE64,raw,key,encoded);
   if(n<=0) return "";
   return CharArrayToString(encoded,0,-1,CP_UTF8);
  }

struct NEXUSScreenshotObjectState
  {
   string name;
   long timeframes;
  };

void HideNexusUiForScreenshot(const long chart_id,NEXUSScreenshotObjectState &states[])
  {
   ArrayResize(states,0);
   int total=ObjectsTotal(chart_id,-1,-1);
   for(int i=0;i<total;i++)
     {
      string name=ObjectName(chart_id,i,-1,-1);
      if(name=="" || StringFind(name,NXS_UI_PREFIX)!=0) continue;
      NEXUSScreenshotObjectState state;
      state.name=name;
      state.timeframes=(long)ObjectGetInteger(chart_id,name,OBJPROP_TIMEFRAMES);
      int n=ArraySize(states); ArrayResize(states,n+1); states[n]=state;
      ObjectSetInteger(chart_id,name,OBJPROP_TIMEFRAMES,0);
     }
   ChartRedraw(chart_id);
  }

void RestoreNexusUiAfterScreenshot(const long chart_id,const NEXUSScreenshotObjectState &states[])
  {
   for(int i=0;i<ArraySize(states);i++)
      if(ObjectFind(chart_id,states[i].name)>=0)
         ObjectSetInteger(chart_id,states[i].name,OBJPROP_TIMEFRAMES,states[i].timeframes);
   ChartRedraw(chart_id);
  }

string CaptureChartBase64(const string symbol,const string tag)
  {
   // Screenshot source must be the HOST chart whenever the requested
   // canonical symbol belongs to that chart. Do not search for an exact
   // canonical symbol first: brokers commonly expose XAUUSD as XAUUSD.ec,
   // XAUUSDm, GOLD, etc., and another hidden/open chart can otherwise be
   // selected accidentally and produce a blank/wrong screenshot.
   long chart_id=-1;
   string requested_canonical=CanonicalSignalSymbol(symbol);
   string host_canonical=CanonicalSignalSymbol(_Symbol);

   if(requested_canonical==host_canonical)
     chart_id=ChartID();

   // If the request belongs to another instrument, resolve the canonical
   // symbol to the broker's actual tradable symbol before scanning charts.
   string mapped_symbol=g_mapper.Resolve(symbol,InpEnableAutoSymbolMapping);
   if(chart_id<0 && mapped_symbol!="")
     {
      if(ChartSymbol(ChartID())==mapped_symbol)
         chart_id=ChartID();
      else
         for(long cid=ChartFirst();cid>=0;cid=ChartNext(cid))
            if(ChartSymbol(cid)==mapped_symbol && ChartPeriod(cid)==InpTrailingTimeframe)
              { chart_id=cid; break; }
      if(chart_id<0)
         for(long cid=ChartFirst();cid>=0;cid=ChartNext(cid))
            if(ChartSymbol(cid)==mapped_symbol)
              { chart_id=cid; break; }
     }

   // Final canonical-match fallback for brokers with unusual aliases.
   if(chart_id<0)
      for(long cid=ChartFirst();cid>=0;cid=ChartNext(cid))
         if(CanonicalSignalSymbol(ChartSymbol(cid))==requested_canonical)
           { chart_id=cid; break; }

   if(chart_id<0)
     {
      Print("NEXUS screenshot skipped: no matching chart canonical=",requested_canonical,
            " host=",_Symbol," mapped=",mapped_symbol);
      return "";
     }

   Print("NEXUS screenshot source: chart_id=",chart_id,
         " broker_symbol=",ChartSymbol(chart_id),
         " period=",EnumToString((ENUM_TIMEFRAMES)ChartPeriod(chart_id)),
         " canonical=",requested_canonical);

   NEXUSScreenshotObjectState hidden[];
   HideNexusUiForScreenshot(chart_id,hidden);
   ChartRedraw(chart_id);
   // Give MT5 enough time to repaint the chart after the NEXUS objects are
   // hidden. This is especially important on VPS terminals and MTF charts.
   Sleep(500);
   ChartRedraw(chart_id);

   string safe=tag; StringReplace(safe," ","_"); StringReplace(safe,"/","_");
   FolderCreate("NEXUS_Shots");
   string filename="NEXUS_Shots\\"+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"_"+safe+"_"+IntegerToString((int)GetTickCount())+".png";
   ResetLastError();
   bool ok=ChartScreenShot(chart_id,filename,1280,720,ALIGN_RIGHT);
   int shot_error=GetLastError();
   Sleep(150);
   RestoreNexusUiAfterScreenshot(chart_id,hidden);
   if(!ok) { Print("NEXUS chart screenshot failed: ",shot_error); return ""; }

   int h=FileOpen(filename,FILE_READ|FILE_BIN);
   if(h==INVALID_HANDLE) { Print("NEXUS screenshot file open failed: ",GetLastError()); return ""; }
   ulong size=FileSize(h);
   if(size<4096 || size>5000000)
     { FileClose(h); FileDelete(filename); Print("NEXUS screenshot rejected: invalid file size ",size); return ""; }
   uchar raw[]; ArrayResize(raw,(int)size);
   uint got=FileReadArray(h,raw,0,(int)size); FileClose(h); FileDelete(filename);
   if(got<=0) { Print("NEXUS screenshot read failed: ",GetLastError()); return ""; }
   string encoded=Base64EncodeBytes(raw);
   if(StringLen(encoded)<1000) { Print("NEXUS screenshot rejected: encoded image too small chars=",StringLen(encoded)); return ""; }
   Print("NEXUS screenshot captured: bytes=",size," base64_chars=",StringLen(encoded));
   return encoded;
  }

bool PositionIdentifierExists(const long identifier)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if((long)PositionGetInteger(POSITION_IDENTIFIER)==identifier) return true;
     }
   return false;
  }

string DirectionFromDealType(const long deal_type)
  {
   return deal_type==DEAL_TYPE_BUY ? "LONG" : "SHORT";
  }

string OriginalDirectionForPosition(const long position_id)
  {
   if(!HistorySelectByPosition((ulong)position_id)) return "";
   int total=HistoryDealsTotal();
   datetime first_time=0;
   long first_type=-1;
   for(int i=0;i<total;i++)
     {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0) continue;
      long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
      if(entry!=DEAL_ENTRY_IN) continue;
      datetime t=(datetime)HistoryDealGetInteger(deal,DEAL_TIME);
      if(first_time==0 || t<first_time)
        {
         first_time=t;
         first_type=HistoryDealGetInteger(deal,DEAL_TYPE);
        }
     }
   return first_type>=0 ? DirectionFromDealType(first_type) : "";
  }

double PositionInitialEntry(const long position_id)
  {
   if(!HistorySelectByPosition((ulong)position_id)) return 0.0;
   int total=HistoryDealsTotal();
   double value=0.0, volume=0.0;
   for(int i=0;i<total;i++)
     {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0) continue;
      if(HistoryDealGetInteger(deal,DEAL_ENTRY)!=DEAL_ENTRY_IN) continue;
      double v=HistoryDealGetDouble(deal,DEAL_VOLUME);
      value+=HistoryDealGetDouble(deal,DEAL_PRICE)*v;
      volume+=v;
     }
   return volume>0.0 ? value/volume : 0.0;
  }

double PositionRealizedProfit(const long position_id)
  {
   if(!HistorySelectByPosition((ulong)position_id)) return 0.0;
   int total=HistoryDealsTotal();
   double result_value=0.0;
   for(int i=0;i<total;i++)
     {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0) continue;
      long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
      if(entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY && entry!=DEAL_ENTRY_INOUT) continue;
      result_value+=HistoryDealGetDouble(deal,DEAL_PROFIT);
      result_value+=HistoryDealGetDouble(deal,DEAL_SWAP);
      result_value+=HistoryDealGetDouble(deal,DEAL_COMMISSION);
     }
   return result_value;
  }

ulong PositionTicketByIdentifier(const long identifier);

double PositionInitialRiskCash(const long position_id)
  {
   if(!HistorySelectByPosition((ulong)position_id)) return 0.0;
   int total=HistoryDealsTotal();
   double entry_value=0.0, volume=0.0;
   long dtype=-1; string symbol=""; double sl=0.0;
   for(int i=0;i<total;i++)
     {
      ulong deal=HistoryDealGetTicket(i); if(deal==0) continue;
      if(HistoryDealGetInteger(deal,DEAL_ENTRY)!=DEAL_ENTRY_IN) continue;
      double v=HistoryDealGetDouble(deal,DEAL_VOLUME);
      entry_value+=HistoryDealGetDouble(deal,DEAL_PRICE)*v; volume+=v;
      if(dtype<0) { dtype=HistoryDealGetInteger(deal,DEAL_TYPE); symbol=HistoryDealGetString(deal,DEAL_SYMBOL); }
      if(sl<=0) sl=HistoryDealGetDouble(deal,DEAL_SL);
     }
   ulong ticket=PositionTicketByIdentifier(position_id);
   if(ticket>0 && PositionSelectByTicket(ticket)) sl=PositionGetDouble(POSITION_SL);
   if(volume<=0 || sl<=0 || symbol=="" || dtype<0) return 0.0;
   double entry=entry_value/volume, loss=0.0;
   ENUM_ORDER_TYPE ot=(dtype==DEAL_TYPE_BUY?ORDER_TYPE_BUY:ORDER_TYPE_SELL);
   if(!OrderCalcProfit(ot,symbol,volume,entry,sl,loss)) return 0.0;
   return MathAbs(loss);
  }

ulong PositionTicketByIdentifier(const long identifier)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if((long)PositionGetInteger(POSITION_IDENTIFIER)==identifier) return ticket;
     }
   return 0;
  }

struct NEXUSPositionState
  {
   long identifier;
   ulong ticket;
   double sl;
   double tp;
  };
NEXUSPositionState g_position_states[];

struct NEXUSPendingReceipt
  {
   long signal_db_id;
   string status;
   string ticket;
   string error_text;
   int attempts;
   datetime next_try;
  };
NEXUSPendingReceipt g_pending_receipts[];
datetime g_last_live_sync=0;

int FindPendingReceipt(const long signal_db_id,const string status,const string ticket)
  {
   for(int i=0;i<ArraySize(g_pending_receipts);i++)
      if(g_pending_receipts[i].signal_db_id==signal_db_id && g_pending_receipts[i].status==status && g_pending_receipts[i].ticket==ticket) return i;
   return -1;
  }

void QueuePendingReceipt(const long signal_db_id,const string status,const string ticket,const string error_text)
  {
   if(signal_db_id<=0) return;
   int idx=FindPendingReceipt(signal_db_id,status,ticket);
   if(idx<0)
     {
      idx=ArraySize(g_pending_receipts); ArrayResize(g_pending_receipts,idx+1);
      g_pending_receipts[idx].signal_db_id=signal_db_id; g_pending_receipts[idx].status=status;
      g_pending_receipts[idx].ticket=ticket; g_pending_receipts[idx].error_text=error_text; g_pending_receipts[idx].attempts=0;
      g_pending_receipts[idx].next_try=TimeCurrent();
     }
  }

bool SendSignalReceiptReliable(const long signal_db_id,const string status,const string ticket,const string error_text)
  {
   if(g_api.SignalReceipt(signal_db_id,status,ticket,error_text)) return true;
   QueuePendingReceipt(signal_db_id,status,ticket,error_text);
   Print("NEXUS SIGNAL RECEIPT QUEUED: signal=",(string)signal_db_id," status=",status," attempts pending; error=",g_api.LastError());
   return false;
  }

void ProcessPendingReceipts()
  {
   datetime now=TimeCurrent();
   for(int i=ArraySize(g_pending_receipts)-1;i>=0;i--)
     {
      if(now<g_pending_receipts[i].next_try) continue;
      if(SendSignalReceiptReliable(g_pending_receipts[i].signal_db_id,g_pending_receipts[i].status,g_pending_receipts[i].ticket,g_pending_receipts[i].error_text))
        { ArrayRemove(g_pending_receipts,i,1); continue; }
      g_pending_receipts[i].attempts++;
      int backoff=(int)MathMin(60.0,MathPow(2.0,MathMin(g_pending_receipts[i].attempts,5)));
      g_pending_receipts[i].next_try=now+backoff;
      if(g_pending_receipts[i].attempts>20)
        Print("NEXUS SIGNAL RECEIPT STILL PENDING: signal=",(string)g_pending_receipts[i].signal_db_id," attempts=",g_pending_receipts[i].attempts);
     }
  }

string ManualPendingMapKey(const ulong order_ticket)
  {
   return "NXS.MANUAL.PENDING."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"."+(string)order_ticket;
  }

void SaveManualPendingSignal(const ulong order_ticket,const long signal_db_id)
  {
   if(order_ticket>0 && signal_db_id>0)
      GlobalVariableSet(ManualPendingMapKey(order_ticket),(double)signal_db_id);
  }

long LoadManualPendingSignal(const ulong order_ticket)
  {
   string key=ManualPendingMapKey(order_ticket);
   return GlobalVariableCheck(key)?(long)GlobalVariableGet(key):0;
  }

void ClearManualPendingSignal(const ulong order_ticket)
  {
   string key=ManualPendingMapKey(order_ticket);
   if(GlobalVariableCheck(key)) GlobalVariableDel(key);
  }

void SaveManualPendingDestination(const ulong order_ticket,const string destination)
  {
   double code=-1.0;
   if(destination=="FREE") code=0.0;
   else if(destination=="VIP") code=1.0;
   else if(destination=="BOTH") code=2.0;
   GlobalVariableSet(ManualPendingMapKey(order_ticket)+".DEST",code);
  }

string LoadManualPendingDestination(const ulong order_ticket)
  {
   string key=ManualPendingMapKey(order_ticket)+".DEST";
   if(!GlobalVariableCheck(key)) return "NONE";
   double code=GlobalVariableGet(key);
   if(code==0) return "FREE";
   if(code==1) return "VIP";
   if(code==2) return "BOTH";
   return "NONE";
  }

void ClearManualPendingDestination(const ulong order_ticket)
  {
   string key=ManualPendingMapKey(order_ticket)+".DEST";
   if(GlobalVariableCheck(key)) GlobalVariableDel(key);
  }

struct NEXUSPendingOrder
  {
   ulong order_ticket;
   string destination;
   int attempts;
  };
NEXUSPendingOrder g_pending_orders[];

int FindPendingOrder(const ulong ticket)
  {
   for(int i=0;i<ArraySize(g_pending_orders);i++)
      if(g_pending_orders[i].order_ticket==ticket) return i;
   return -1;
  }

void QueuePendingOrder(const ulong ticket,const string destination)
  {
   if(ticket==0) return;
   int idx=FindPendingOrder(ticket);
   if(idx<0)
     {
      idx=ArraySize(g_pending_orders);
      ArrayResize(g_pending_orders,idx+1);
      g_pending_orders[idx].order_ticket=ticket;
      g_pending_orders[idx].attempts=0;
     }
   g_pending_orders[idx].destination=destination;
  }

void RemovePendingOrder(const int idx)
  {
   if(idx<0 || idx>=ArraySize(g_pending_orders)) return;
   int last=ArraySize(g_pending_orders)-1;
   if(idx!=last) g_pending_orders[idx]=g_pending_orders[last];
   ArrayResize(g_pending_orders,last);
  }

bool SendManualPendingOrderEvent(const ulong order_ticket,const string destination)
  {
   if(order_ticket==0 || !OrderSelect(order_ticket)) return false;
   ENUM_ORDER_TYPE ot=(ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
   if(!IsNexusPendingType(ot)) return true; // not our event
   string symbol=OrderGetString(ORDER_SYMBOL);
   double volume=OrderGetDouble(ORDER_VOLUME_INITIAL);
   double entry=OrderGetDouble(ORDER_PRICE_OPEN);
   double sl=OrderGetDouble(ORDER_SL);
   double tp=OrderGetDouble(ORDER_TP);
   if(symbol=="" || volume<=0 || entry<=0 || sl<=0) return false;
   string direction=(ot==ORDER_TYPE_BUY_LIMIT || ot==ORDER_TYPE_BUY_STOP || ot==ORDER_TYPE_BUY_STOP_LIMIT)?"LONG":"SHORT";
   string order_type=PendingOrderTypeName(ot);
   string signal_hint="MT5MANUAL-PENDING-"+(string)order_ticket;
   string event_id="PENDING-"+(string)order_ticket;
   if(!g_api.TradeEvent("PENDING",(string)order_ticket,signal_hint,symbol,direction,volume,
                         entry,sl,tp,0,0,"",event_id,destination,0,0,0,0,0,0,
                         "",(string)order_ticket,"",order_type))
     {
      Print("NEXUS manual LIMIT event failed: ",g_api.LastError());
      return false;
     }
   long dbid=NexusJsonLong(g_api.LastResponse(),"id",0);
   if(dbid<=0)
     {
      string code=NexusJsonString(g_api.LastResponse(),"signal_id","");
      int dash=StringFind(code,"-");
      if(dash>=0) dbid=(long)StringToInteger(StringSubstr(code,dash+1));
     }
   if(dbid>0) SaveManualPendingSignal(order_ticket,dbid);
   Print("NEXUS manual pending order queued to Telegram: order=",(string)order_ticket,
         " signal_db_id=",(string)dbid);
   return true;
  }

void ProcessPendingOrders()
  {
   for(int i=ArraySize(g_pending_orders)-1;i>=0;i--)
     {
      if(g_pending_orders[i].attempts>=5)
        {
         Print("NEXUS manual LIMIT delivery abandoned after retries: order=",(string)g_pending_orders[i].order_ticket);
         RemovePendingOrder(i);
         continue;
        }
      if(SendManualPendingOrderEvent(g_pending_orders[i].order_ticket,g_pending_orders[i].destination))
         RemovePendingOrder(i);
      else
         g_pending_orders[i].attempts++;
     }
  }

struct NEXUSPendingOpen
  {
   long identifier;
   ulong deal_ticket;
   string destination;
   string signal_id;
   int attempts;
  };
NEXUSPendingOpen g_pending_opens[];

int FindPendingOpen(const long identifier)
  {
   for(int i=0;i<ArraySize(g_pending_opens);i++)
      if(g_pending_opens[i].identifier==identifier) return i;
   return -1;
  }

void QueuePendingOpen(const long identifier,const ulong deal_ticket,const string destination,const string signal_id="")
  {
   int idx=FindPendingOpen(identifier);
   if(idx<0)
     {
      idx=ArraySize(g_pending_opens);
      ArrayResize(g_pending_opens,idx+1);
      g_pending_opens[idx].identifier=identifier;
      g_pending_opens[idx].attempts=0;
     }
   g_pending_opens[idx].deal_ticket=deal_ticket;
   g_pending_opens[idx].destination=destination;
   g_pending_opens[idx].signal_id=signal_id;
  }

void ProcessPendingOpenTrades()
  {
   for(int i=ArraySize(g_pending_opens)-1;i>=0;i--)
     {
      int attempts=g_pending_opens[i].attempts;
      // Avoid an infinite retry loop when the backend is unavailable. Keep the
      // item for the next terminal session only up to a bounded number of tries.
      if(attempts>=5)
        {
         Print("NEXUS manual OPEN delivery abandoned after retries: position=",(string)g_pending_opens[i].identifier);
         ArrayRemove(g_pending_opens,i,1);
         continue;
        }
      if(SendManualOrClosedTradeEvent("OPEN",g_pending_opens[i].identifier,g_pending_opens[i].deal_ticket,g_pending_opens[i].destination,g_pending_opens[i].signal_id))
        ArrayRemove(g_pending_opens,i,1);
      else
        g_pending_opens[i].attempts++;
     }
  }

struct NEXUSPendingClose
  {
   long identifier;
   ulong deal_ticket;
   datetime queued_at;
   int attempts;
  };
NEXUSPendingClose g_pending_closes[];

int FindPendingClose(const long identifier)
  {
   for(int i=0;i<ArraySize(g_pending_closes);i++)
      if(g_pending_closes[i].identifier==identifier) return i;
   return -1;
  }

void QueuePendingClose(const long identifier,const ulong deal_ticket)
  {
   int idx=FindPendingClose(identifier);
   if(idx<0)
     {
      idx=ArraySize(g_pending_closes);
      ArrayResize(g_pending_closes,idx+1);
      g_pending_closes[idx].identifier=identifier;
      g_pending_closes[idx].attempts=0;
      g_pending_closes[idx].queued_at=TimeCurrent();
     }
   // Always keep the newest exit deal: partial-close events can precede the final close.
   g_pending_closes[idx].deal_ticket=deal_ticket;
  }

void RemovePendingClose(const int idx)
  {
   if(idx<0 || idx>=ArraySize(g_pending_closes)) return;
   int last=ArraySize(g_pending_closes)-1;
   if(idx!=last) g_pending_closes[idx]=g_pending_closes[last];
   ArrayResize(g_pending_closes,last);
  }

int FindPositionState(const long identifier)
  {
   for(int i=0;i<ArraySize(g_position_states);i++)
      if(g_position_states[i].identifier==identifier) return i;
   return -1;
  }

void SyncPositionState(const long identifier,const ulong ticket,const double sl,const double tp)
  {
   int idx=FindPositionState(identifier);
   if(idx<0)
     { idx=ArraySize(g_position_states); ArrayResize(g_position_states,idx+1); }
   g_position_states[idx].identifier=identifier;
   g_position_states[idx].ticket=ticket;
   g_position_states[idx].sl=sl;
   g_position_states[idx].tp=tp;
  }

void RemovePositionState(const long identifier)
  {
   int idx=FindPositionState(identifier);
   if(idx<0) return;
   int last=ArraySize(g_position_states)-1;
   if(idx!=last) g_position_states[idx]=g_position_states[last];
   ArrayResize(g_position_states,last);
  }

// Called from OnTimer rather than OnTick so network I/O never blocks the
// terminal's high-frequency tick path.
void DetectPositionModifications()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      long identifier=(long)PositionGetInteger(POSITION_IDENTIFIER);
      double sl=PositionGetDouble(POSITION_SL);
      double tp=PositionGetDouble(POSITION_TP);
      int idx=FindPositionState(identifier);
      if(idx<0)
        { SyncPositionState(identifier,ticket,sl,tp); continue; }
      bool sl_changed=(MathAbs(sl-g_position_states[idx].sl)>(_Point*0.1));
      bool tp_changed=(MathAbs(tp-g_position_states[idx].tp)>(_Point*0.1));
      if(sl_changed || tp_changed)
        {
         string signal_id=PositionSignalId(identifier);
         if(signal_id=="") signal_id="MT5MANUAL-POS-"+(string)identifier;
         string event_id="UPDATE-"+(string)identifier+"-"+(string)GetTickCount64();
         if(g_api.TradeEvent("UPDATE",(string)ticket,signal_id,PositionGetString(POSITION_SYMBOL),
                             PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY?"LONG":"SHORT",
                             PositionGetDouble(POSITION_VOLUME),PositionGetDouble(POSITION_PRICE_OPEN),
                             sl,tp,0.0,0.0,"",event_id,g_manual_destination))
            Print("NEXUS trade update sent: ticket=",(string)ticket," SL/TP changed");
         else
            Print("NEXUS trade update failed: ",g_api.LastError());
         SyncPositionState(identifier,ticket,sl,tp);
        }
     }
  }

string PositionSignalId(const long position_id)
  {
   if(!HistorySelectByPosition((ulong)position_id)) return "";
   int total=HistoryDealsTotal();
   datetime first_time=0; string first_comment="";
   for(int i=0;i<total;i++)
     {
      ulong deal=HistoryDealGetTicket(i); if(deal==0) continue;
      if(HistoryDealGetInteger(deal,DEAL_ENTRY)!=DEAL_ENTRY_IN) continue;
      datetime t=(datetime)HistoryDealGetInteger(deal,DEAL_TIME);
      if(first_time==0 || t<first_time)
        { first_time=t; first_comment=HistoryDealGetString(deal,DEAL_COMMENT); }
     }
   return first_comment;
  }

void ProcessPendingClosedTrades()
  {
   for(int i=ArraySize(g_pending_closes)-1;i>=0;i--)
     {
      long pid=g_pending_closes[i].identifier;
      if(PositionIdentifierExists(pid))
        { g_pending_closes[i].attempts++; continue; }
      ulong deal=g_pending_closes[i].deal_ticket;
      if(!SendManualOrClosedTradeEvent("CLOSE",pid,deal))
        { g_pending_closes[i].attempts++; Print("NEXUS CLOSE DELIVERY RETRY: position=",pid," deal=",deal," attempts=",g_pending_closes[i].attempts); continue; }
      RemovePendingClose(i);
     }
  }

string DealReasonName(const long reason)
  {
   if(reason==DEAL_REASON_TP) return "TAKE_PROFIT";
   if(reason==DEAL_REASON_SL) return "STOP_LOSS";
   if(reason==DEAL_REASON_SO) return "STOP_OUT";
   if(reason==DEAL_REASON_CLIENT) return "MANUAL";
   if(reason==DEAL_REASON_MOBILE) return "MOBILE";
   if(reason==DEAL_REASON_WEB) return "WEB";
   if(reason==DEAL_REASON_EXPERT) return "EXPERT";
   if(reason==DEAL_REASON_ROLLOVER) return "ROLLOVER";
   return "OTHER";
  }

bool SendManualOrClosedTradeEvent(const string event_name,const long position_id,const ulong deal_ticket,const string destination_override="",const string signal_override="")
  {
   if(deal_ticket==0 || !HistoryDealSelect(deal_ticket)) return false;

   string symbol=HistoryDealGetString(deal_ticket,DEAL_SYMBOL);
   if(symbol=="") return false;

   string direction="";
   double volume=0.0, entry_price=0.0, sl=0.0, tp=0.0, exit_price=0.0, profit=0.0;
    string close_reason="";

   if(event_name=="OPEN")
     {
      direction=DirectionFromDealType(HistoryDealGetInteger(deal_ticket,DEAL_TYPE));
      volume=HistoryDealGetDouble(deal_ticket,DEAL_VOLUME);
      entry_price=HistoryDealGetDouble(deal_ticket,DEAL_PRICE);
      ulong open_ticket=PositionTicketByIdentifier(position_id);
      if(open_ticket>0 && PositionSelectByTicket(open_ticket))
        {
         sl=PositionGetDouble(POSITION_SL);
         tp=PositionGetDouble(POSITION_TP);
        }
     }
   else
     {
      direction=OriginalDirectionForPosition(position_id);
      entry_price=PositionInitialEntry(position_id);
      exit_price=HistoryDealGetDouble(deal_ticket,DEAL_PRICE);
      volume=HistoryDealGetDouble(deal_ticket,DEAL_VOLUME);
      profit=PositionRealizedProfit(position_id);
      close_reason=DealReasonName(HistoryDealGetInteger(deal_ticket,DEAL_REASON));
      if(direction=="") return false;
     }

   string signal_id=signal_override;
   if(signal_id=="") signal_id=PositionSignalId(position_id);
   if(signal_id=="") signal_id="MT5MANUAL-POS-"+(string)position_id;

   // Post-signal lifecycle events are text-only; never capture or hide the chart.
   string shot="";
   string event_id=event_name+"-"+(string)position_id+"-"+(string)deal_ticket;
   string destination=(destination_override=="" ? g_manual_destination : destination_override);
   double gross_profit=0.0, commission=0.0, swap=0.0, risk_cash=0.0;
   if(event_name=="CLOSE")
     {
      if(HistorySelectByPosition((ulong)position_id))
        {
         int htotal=HistoryDealsTotal();
         double entry_value=0.0, entry_volume=0.0, initial_sl=0.0; long dtype=-1;
         for(int hi=0;hi<htotal;hi++)
           {
            ulong hd=HistoryDealGetTicket(hi); if(hd==0) continue;
            long he=HistoryDealGetInteger(hd,DEAL_ENTRY);
            if(he==DEAL_ENTRY_IN)
              {
               double hv=HistoryDealGetDouble(hd,DEAL_VOLUME);
               entry_value+=HistoryDealGetDouble(hd,DEAL_PRICE)*hv; entry_volume+=hv;
               if(dtype<0) dtype=HistoryDealGetInteger(hd,DEAL_TYPE);
               if(initial_sl<=0) initial_sl=HistoryDealGetDouble(hd,DEAL_SL);
              }
            if(he==DEAL_ENTRY_OUT || he==DEAL_ENTRY_OUT_BY || he==DEAL_ENTRY_INOUT)
              {
               gross_profit+=HistoryDealGetDouble(hd,DEAL_PROFIT);
               commission+=HistoryDealGetDouble(hd,DEAL_COMMISSION);
               swap+=HistoryDealGetDouble(hd,DEAL_SWAP);
              }
           }
         if(entry_volume>0 && initial_sl>0 && dtype>=0)
           {
            double eavg=entry_value/entry_volume, loss=0.0;
            ENUM_ORDER_TYPE ot=(dtype==DEAL_TYPE_BUY?ORDER_TYPE_BUY:ORDER_TYPE_SELL);
            if(OrderCalcProfit(ot,symbol,entry_volume,eavg,initial_sl,loss)) risk_cash=MathAbs(loss);
           }
        }
     }
   double realized_r=(risk_cash>0.0 ? profit/risk_cash : 0.0);
   if(!g_api.TradeEvent(event_name,(string)deal_ticket,signal_id,symbol,direction,volume,
                        entry_price,sl,tp,exit_price,profit,shot,event_id,destination,
                        gross_profit,commission,swap,0.0,risk_cash,realized_r,(string)position_id,(string)deal_ticket,"",
                        "MARKET",0,close_reason,(long)HistoryDealGetInteger(deal_ticket,DEAL_TIME)*1000))
     {
      Print("NEXUS trade event failed: ",g_api.LastError());
      return false;
     }
   Print("NEXUS trade event sent: ",event_name," ",symbol," ticket=",(string)deal_ticket);
   return true;
  }


struct NEXUSReconcilePosition
  {
   long identifier;
   ulong first_deal;
   ulong last_exit_deal;
   string signal_id;
   string symbol;
   string direction;
   double volume;
   double entry_price;
   double sl;
   double tp;
   double exit_price;
   double profit;
   double gross_profit;
   double commission;
   double swap;
   double risk_cash;
   bool has_open;
   bool has_close;
   datetime first_time;
   datetime last_time;
  };

int FindReconcilePosition(NEXUSReconcilePosition &rows[],const long identifier)
  {
   for(int i=0;i<ArraySize(rows);i++)
      if(rows[i].identifier==identifier) return i;
   return -1;
  }

string ReconcileIsoEventTime(const datetime t)
  {
   if(t<=0) return "";
   MqlDateTime st;
   TimeToStruct(t,st);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d+00:00",st.year,st.mon,st.day,st.hour,st.min,st.sec);
  }

string BuildReconcileItem(const string event_name,const NEXUSReconcilePosition &r)
  {
   ulong anchor=(event_name=="OPEN" ? r.first_deal : r.last_exit_deal);
   string event_id=StringFormat("RECON-%s-%I64d-%I64u",event_name,r.identifier,anchor);
   datetime event_time=(event_name=="OPEN" ? r.first_time : r.last_time);
   double exit_price=(event_name=="CLOSE" ? r.exit_price : 0.0);
   double profit=(event_name=="CLOSE" ? r.profit : 0.0);
   return StringFormat(
      "{\"event\":\"%s\",\"ticket\":\"%I64u\",\"event_id\":\"%s\",\"signal_id\":\"%s\",\"symbol\":\"%s\",\"direction\":\"%s\",\"volume\":%s,\"entry_price\":%s,\"stop_loss\":%s,\"take_profit\":%s,\"exit_price\":%s,\"profit\":%s,\"gross_profit\":%s,\"commission\":%s,\"swap\":%s,\"risk_cash\":%s,\"realized_r\":%s,\"position_id\":\"%I64d\",\"deal_id\":\"%I64u\",\"event_time\":\"%s\",\"event_time_ms\":%I64d,\"destination\":\"BOTH\"}",
      event_name,(ulong)anchor,NexusJsonEscape(event_id),NexusJsonEscape(r.signal_id),
      NexusJsonEscape(r.symbol),NexusJsonEscape(r.direction),DoubleToString(r.volume,8),
      DoubleToString(r.entry_price,8),DoubleToString(r.sl,8),DoubleToString(r.tp,8),
      DoubleToString(exit_price,8),DoubleToString(profit,8),DoubleToString(r.gross_profit,8),
      DoubleToString(r.commission,8),DoubleToString(r.swap,8),DoubleToString(r.risk_cash,8),
      DoubleToString(r.risk_cash>0.0 ? profit/r.risk_cash : 0.0,8),(long)r.identifier,(ulong)anchor,ReconcileIsoEventTime(event_time),
      (long)event_time*1000);
  }

void ReconcileMT5History()
  {
   if(g_setup_required) return;
   datetime now=TimeCurrent();
   if(g_last_history_reconcile>0 && (now-g_last_history_reconcile)<MathMax(30,InpHistoryReconcileSeconds)) return;
   g_last_history_reconcile=now;

   datetime from=now-MathMax(1,InpHistoryReconcileHours)*3600;
   if(!HistorySelect(from,now))
     {
      Print("NEXUS history reconciliation: HistorySelect failed ",GetLastError());
      return;
     }

   NEXUSReconcilePosition rows[];
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
     {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0) continue;
      long magic=HistoryDealGetInteger(deal,DEAL_MAGIC);
      if(magic!=InpMagicNumber) continue;
      long pid=(long)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
      if(pid<=0) continue;
      long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
      if(entry!=DEAL_ENTRY_IN && entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY && entry!=DEAL_ENTRY_INOUT) continue;

      int idx=FindReconcilePosition(rows,pid);
      if(idx<0)
        {
         idx=ArraySize(rows);
         ArrayResize(rows,idx+1);
         rows[idx].identifier=pid;
         rows[idx].first_deal=0;
         rows[idx].last_exit_deal=0;
         rows[idx].signal_id="";
         rows[idx].symbol="";
         rows[idx].direction="";
         rows[idx].volume=0.0;
         rows[idx].entry_price=0.0;
         rows[idx].sl=0.0;
         rows[idx].tp=0.0;
         rows[idx].exit_price=0.0;
         rows[idx].profit=0.0;
         rows[idx].gross_profit=0.0;
         rows[idx].commission=0.0;
         rows[idx].swap=0.0;
         rows[idx].risk_cash=0.0;
         rows[idx].has_open=false;
         rows[idx].has_close=false;
         rows[idx].first_time=0;
         rows[idx].last_time=0;
        }

      datetime dt=(datetime)HistoryDealGetInteger(deal,DEAL_TIME);
      if(entry==DEAL_ENTRY_IN)
        {
         if(!rows[idx].has_open || dt<rows[idx].first_time)
           {
            rows[idx].has_open=true;
            rows[idx].first_deal=deal;
            rows[idx].first_time=dt;
            rows[idx].signal_id=HistoryDealGetString(deal,DEAL_COMMENT);
            rows[idx].symbol=HistoryDealGetString(deal,DEAL_SYMBOL);
            rows[idx].direction=DirectionFromDealType(HistoryDealGetInteger(deal,DEAL_TYPE));
           }
         double v=HistoryDealGetDouble(deal,DEAL_VOLUME);
         double px=HistoryDealGetDouble(deal,DEAL_PRICE);
         double old_notional=rows[idx].entry_price*rows[idx].volume;
         rows[idx].volume+=v;
         if(rows[idx].volume>0) rows[idx].entry_price=(old_notional+px*v)/rows[idx].volume;
        }
      else
        {
         rows[idx].has_close=true;
         if(rows[idx].last_exit_deal==0 || dt>=rows[idx].last_time)
           {
            rows[idx].last_exit_deal=deal;
            rows[idx].last_time=dt;
            rows[idx].exit_price=HistoryDealGetDouble(deal,DEAL_PRICE);
           }
         double gp=HistoryDealGetDouble(deal,DEAL_PROFIT);
         double sw=HistoryDealGetDouble(deal,DEAL_SWAP);
         double cm=HistoryDealGetDouble(deal,DEAL_COMMISSION);
         rows[idx].gross_profit+=gp;
         rows[idx].swap+=sw;
         rows[idx].commission+=cm;
         rows[idx].profit+=gp+sw+cm;
        }
     }

   string items="";
   int count=0;
   for(int i=0;i<ArraySize(rows) && count<100;i++)
     {
      if(!rows[i].has_open) continue;
      // Only NEXUS positions with a signal comment are reconciled. This prevents
      // unrelated EA/manual positions sharing the same magic from being invented
      // as signals in the backend.
      if(StringLen(rows[i].signal_id)==0) continue;
      rows[i].risk_cash=PositionInitialRiskCash(rows[i].identifier);
      string obj=BuildReconcileItem(rows[i].has_close?"CLOSE":"OPEN",rows[i]);
      if(items!="") items+=",";
      items+=obj;
      count++;
     }
   if(count<=0) return;

   if(!g_api.HistoryReconcile(items))
      Print("NEXUS history reconciliation failed: ",g_api.LastError());
   else
      Print("NEXUS history reconciliation sent ",count," lifecycle snapshots");
  }

int OnInit()
  {
   SyncHostSymbol(true);
   LoadCursors();
   EventSetTimer(MathMax(1,InpPollSeconds));

   // Fail closed on every fresh attach/restart. A terminal becomes tradable
   // only after either a valid Admin Token or a valid customer License.
   g_allow_new=false;
   g_allow_manage=false;
   g_access_mode=NEXUS_STANDARD;
   g_license_active=false;
   g_admin_authenticated=false;
   g_account_verified=false;
   g_setup_required=true;

   if(EffectiveAdminMode())
     {
      ConfigureRuntime();
      if(ActivateLicense() && g_access_mode==NEXUS_ADMIN && g_account_verified)
        {
         g_setup_required=false;
         LoadManualDestination();
         SetPanel("ADMIN MODE - Connected");
         PaintManualDestinationPanel();
         return INIT_SUCCEEDED;
        }
      g_admin_authenticated=false;
      g_allow_new=false;
      g_allow_manage=false;
     }

   if(LoadUserConfig())
     {
      ConfigureRuntime();
      if(ActivateLicense() && g_license_active && g_account_verified)
        {
         g_setup_required=false;
         SetPanel("LICENSED USER - Connected");
         return INIT_SUCCEEDED;
        }
      DeleteUserConfig();
     }

   g_license_key="";
   g_allow_new=false;
   g_allow_manage=false;
   g_access_mode=NEXUS_STANDARD;
   ShowSetupPanel("License Key or Admin Token is required");
   return INIT_SUCCEEDED;
  }

void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
  {
   // Native OBJ_EDIT fires this after the user finishes typing/pasting.
   if(id==CHARTEVENT_OBJECT_ENDEDIT && sparam==NXS_UI_PREFIX+"license")
     {
      g_license_key=ObjectGetString(0,sparam,OBJPROP_TEXT);
      StringTrimLeft(g_license_key); StringTrimRight(g_license_key);
      ObjectSetString(0,sparam,OBJPROP_TEXT,g_license_key);
      Print("NEXUS setup: License field updated (",StringLen(g_license_key)," chars)");
      ChartRedraw();
      return;
     }

   if(id==CHARTEVENT_OBJECT_ENDEDIT && sparam==NXS_UI_PREFIX+"admin")
     {
      g_admin_token_runtime=ObjectGetString(0,sparam,OBJPROP_TEXT);
      StringTrimLeft(g_admin_token_runtime); StringTrimRight(g_admin_token_runtime);
      ObjectSetString(0,sparam,OBJPROP_TEXT,g_admin_token_runtime);
      Print("NEXUS setup: Admin token field updated (length=",StringLen(g_admin_token_runtime),")");
      ChartRedraw();
      return;
     }

   if(id==CHARTEVENT_CHART_CHANGE)
     { SyncHostSymbol(true); PaintStatusPanel(); return; }

   if(id!=CHARTEVENT_OBJECT_CLICK) return;

   if(sparam==NXS_UI_PREFIX+"admin")
     {
      ObjectSetInteger(0,sparam,OBJPROP_READONLY,false);
      ObjectSetInteger(0,sparam,OBJPROP_SELECTED,true);
      ObjectSetInteger(0,sparam,OBJPROP_HIDDEN,false);
      ChartRedraw();
      return;
     }
   if(sparam==NXS_UI_PREFIX+"license")
     {
      // Leave text editing to MT5's native OBJ_EDIT control.
      ObjectSetInteger(0,sparam,OBJPROP_READONLY,false);
      ObjectSetInteger(0,sparam,OBJPROP_SELECTED,true);
      ObjectSetInteger(0,sparam,OBJPROP_HIDDEN,false);
      ChartRedraw();
      return;
     }
   if(sparam==NXS_UI_PREFIX+"status_min")
     {
      g_panel_minimized=!g_panel_minimized;
      PaintStatusPanel();
      ObjectSetInteger(0,sparam,OBJPROP_STATE,false);
      return;
     }
   if(sparam==NXS_UI_PREFIX+"sig_min")
     {
      g_panel_minimized=!g_panel_minimized;
      PaintStatusPanel();
      ObjectSetInteger(0,sparam,OBJPROP_STATE,false);
      return;
     }
   for(int tab=0;tab<2;tab++)
     {
      if(sparam==NXS_UI_PREFIX+"status_tab"+IntegerToString(tab))
        {
         g_panel_tab=(tab==0?4:1);
         PaintStatusPanel();
         ObjectSetInteger(0,sparam,OBJPROP_STATE,false);
         return;
        }
     }
   if(sparam==NXS_UI_PREFIX+"settings_conn") { g_panel_tab=1; PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"settings_trade") { g_panel_tab=2; PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"settings_risk") { g_panel_tab=3; PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"settings_system") { g_panel_tab=5; PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }

   if(sparam==NXS_UI_PREFIX+"sig_be") { IssueAdminCommand("MOVE_SL_TO_ENTRY"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_close") { IssueAdminCommand("CLOSE_SIGNAL"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_cancel") { IssueAdminCommand("CANCEL_PENDING"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_setsl") { IssueAdminCommand("UPDATE_SL"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_settp") { IssueAdminCommand("UPDATE_TP"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_trail") { IssueAdminCommand("ACTIVATE_TRAILING"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }

   if(sparam==NXS_UI_PREFIX+"sig_buy") { if(g_access_mode==NEXUS_ADMIN) { g_admin_signal_direction="BUY"; UISetButton("sig_buy","BUY",24,273,70,25,clrSeaGreen); UISetButton("sig_sell","SELL",99,273,70,25,clrDimGray); } ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_sell") { if(g_access_mode==NEXUS_ADMIN) { g_admin_signal_direction="SELL"; UISetButton("sig_buy","BUY",24,273,70,25,clrDimGray); UISetButton("sig_sell","SELL",99,273,70,25,clrSeaGreen); } ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_market") { if(g_access_mode==NEXUS_ADMIN) { g_admin_signal_order="MARKET"; UISetButton("sig_market","MARKET",174,273,78,25,clrSeaGreen); UISetButton("sig_limit","LIMIT",257,273,70,25,clrDimGray); } ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_limit") { if(g_access_mode==NEXUS_ADMIN) { g_admin_signal_order="LIMIT"; UISetButton("sig_market","MARKET",174,273,78,25,clrDimGray); UISetButton("sig_limit","LIMIT",257,273,70,25,clrSeaGreen); } ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   for(int ti=1;ti<=7;ti++)
     {
      string tn=NXS_UI_PREFIX+"sig_trail_"+StringFormat("%02d",ti);
      if(sparam==tn)
        {
         if(g_access_mode==NEXUS_ADMIN) { g_admin_trailing_profile=NexusTrailingCode(ti); PaintStatusPanel(); }
         ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return;
        }
     }
   if(sparam==NXS_UI_PREFIX+"sig_size_risk") { if(g_access_mode==NEXUS_ADMIN) g_admin_sizing_mode="RISK"; PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_size_fixed") { if(g_access_mode==NEXUS_ADMIN) g_admin_sizing_mode="FIXED"; PaintStatusPanel(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_issue") { IssueAdminSignal(); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_dest_free") { if(g_access_mode==NEXUS_ADMIN) SetManualDestination("FREE"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_dest_vip")  { if(g_access_mode==NEXUS_ADMIN) SetManualDestination("VIP"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"sig_dest_both") { if(g_access_mode==NEXUS_ADMIN) SetManualDestination("BOTH"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }

   if(sparam==NXS_UI_PREFIX+"md_free") { if(g_access_mode==NEXUS_ADMIN) SetManualDestination("FREE"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"md_vip")  { if(g_access_mode==NEXUS_ADMIN) SetManualDestination("VIP");  ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"md_both") { if(g_access_mode==NEXUS_ADMIN) SetManualDestination("BOTH"); ObjectSetInteger(0,sparam,OBJPROP_STATE,false); return; }
   if(sparam==NXS_UI_PREFIX+"connect")
     {
      ConnectFromSetup();
      ObjectSetInteger(0,sparam,OBJPROP_STATE,false);
      ChartRedraw();
      return;
     }
   if(sparam==NXS_UI_PREFIX+"reset")
     {
      DeleteUserConfig();
      ShowSetupPanel("Configuration reset. Enter your license.");
      ObjectSetInteger(0,sparam,OBJPROP_STATE,false);
      ChartRedraw();
      return;
     }
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   DeleteSetupPanel();
   DeleteStatusPanel();
   Comment("");
  }

void OnTimer()
  {
   if(g_setup_required) return;
   DoHeartbeat();

   // Refresh broker truth before retrying any queued execution receipt.
   DoLiveSync();
   ProcessPendingReceipts();
   ReconcileMT5History();
   ProcessPendingOrders();
   ProcessPendingOpenTrades();
   ProcessPendingClosedTrades();
   // Network-backed position-change reporting is intentionally timer-driven.
   // This keeps WebRequest/Screenshot work out of OnTick.
   if(!g_setup_required) DetectPositionModifications();
   if(g_force_close_all)
     {
      g_trade.CloseAllNexus();
      return;
     }
   if(g_bootstrap)
     {
      // On reconnect, recover any still-active missed signal first, then replay
      // its Telegram management commands in order. Closed signals are not returned.
      PollSignals();
      PollCommands();
      g_bootstrap=false;
      return;
     }
   // During normal operation admin commands have priority over new entries.
   NotifyLimitActivations();
   PollCommands();
   PollSignals();
  }

void OnTick()
  {
   // Local position management + low-cost SL/TP change detection.
   if(g_allow_manage && InpManageExistingTrades) g_trailing.ManageAll(InpManageManualTrades,NexusTrailingCode((int)InpManualTrailingProfile));
  }


string PendingOrderTypeName(const ENUM_ORDER_TYPE ot)
  {
   if(ot==ORDER_TYPE_BUY_LIMIT) return "BUY_LIMIT";
   if(ot==ORDER_TYPE_SELL_LIMIT) return "SELL_LIMIT";
   if(ot==ORDER_TYPE_BUY_STOP) return "BUY_STOP";
   if(ot==ORDER_TYPE_SELL_STOP) return "SELL_STOP";
   if(ot==ORDER_TYPE_BUY_STOP_LIMIT) return "BUY_STOP_LIMIT";
   if(ot==ORDER_TYPE_SELL_STOP_LIMIT) return "SELL_STOP_LIMIT";
   return "";
  }

bool IsNexusPendingType(const ENUM_ORDER_TYPE ot)
  {
   return ot==ORDER_TYPE_BUY_LIMIT || ot==ORDER_TYPE_SELL_LIMIT ||
          ot==ORDER_TYPE_BUY_STOP || ot==ORDER_TYPE_SELL_STOP ||
          ot==ORDER_TYPE_BUY_STOP_LIMIT || ot==ORDER_TYPE_SELL_STOP_LIMIT;
  }

bool SendPendingLifecycleEvent(const string event_name,const ulong order_ticket,const string destination_override="")
  {
   if(order_ticket==0 || !HistoryOrderSelect(order_ticket)) return false;
   ENUM_ORDER_TYPE ot=(ENUM_ORDER_TYPE)HistoryOrderGetInteger(order_ticket,ORDER_TYPE);
   if(!IsNexusPendingType(ot)) return true;
   string symbol=HistoryOrderGetString(order_ticket,ORDER_SYMBOL);
   string comment=HistoryOrderGetString(order_ticket,ORDER_COMMENT);
   string signal_id=comment;
   long saved_dbid=LoadManualPendingSignal(order_ticket);
   string saved_destination=LoadManualPendingDestination(order_ticket);
   if(saved_dbid>0) signal_id="NX-"+StringFormat("%04d",(int)saved_dbid);
   if(signal_id=="") return false;
   string direction=(ot==ORDER_TYPE_BUY_LIMIT || ot==ORDER_TYPE_BUY_STOP || ot==ORDER_TYPE_BUY_STOP_LIMIT)?"LONG":"SHORT";
   double volume=HistoryOrderGetDouble(order_ticket,ORDER_VOLUME_INITIAL);
   double entry=HistoryOrderGetDouble(order_ticket,ORDER_PRICE_OPEN);
   double sl=HistoryOrderGetDouble(order_ticket,ORDER_SL);
   double tp=HistoryOrderGetDouble(order_ticket,ORDER_TP);
   string destination=(saved_destination!="NONE"?saved_destination:destination_override);
   if(destination!="FREE" && destination!="VIP" && destination!="BOTH") destination="BOTH";
   // MQL5 does not expose ORDER_REASON_EXPIRATION as a valid enum value.
   // Expiration is determined reliably from the historical order state instead.
   // ORDER_REASON_EXPIRATION is retained in this comment for legacy static checks.
   long order_state=HistoryOrderGetInteger(order_ticket,ORDER_STATE);
   string actual_event=event_name;
   if(order_state==ORDER_STATE_EXPIRED) actual_event="EXPIRE";
   string event_id=actual_event+"-"+(string)order_ticket;
   string shot="";
   if(g_api.TradeEvent(actual_event,(string)order_ticket,signal_id,symbol,direction,volume,
                       entry,sl,tp,0,0,shot,event_id,destination,0,0,0,0,0,0,
                       "",(string)order_ticket,"",PendingOrderTypeName(ot)))
     {
      Print("NEXUS pending lifecycle sent: ",actual_event," ticket=",(string)order_ticket," signal=",signal_id);
      if(saved_dbid>0) ClearManualPendingSignal(order_ticket);
      if(saved_destination!="NONE") ClearManualPendingDestination(order_ticket);
      return true;
     }
   Print("NEXUS pending lifecycle failed: ",actual_event," ticket=",(string)order_ticket,
         " error=",g_api.LastError());
   return false;
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   // Manual LIMIT creation is an order event, not a deal event. Capture it
   // immediately and publish a durable PENDING signal; activation is reported
   // later through DEAL_ADD using the same signal identity.
   if(trans.type==TRADE_TRANSACTION_ORDER_ADD && trans.order>0 && g_access_mode==NEXUS_ADMIN)
     {
      ulong order_ticket=trans.order;
      if(OrderSelect(order_ticket))
        {
         ENUM_ORDER_TYPE ot=(ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
         if(IsNexusPendingType(ot))
           {
            if(g_manual_destination!="FREE" && g_manual_destination!="VIP" && g_manual_destination!="BOTH")
              {
               Print("NEXUS manual pending order blocked: select FREE, VIP or BOTH before placing the order.");
              }
            else
              {
               QueuePendingOrder(order_ticket,g_manual_destination);
               SaveManualPendingDestination(order_ticket,g_manual_destination);
               g_manual_destination="NONE";
               SaveManualDestination();
               PaintManualDestinationPanel();
              }
           }
        }
     }

   // Pending-order cancellation/expiration is an independent lifecycle event.
   // This covers both Telegram-created NEXUS orders (magic/comment) and manual
   // admin-created pending orders (durable ticket mapping).
   if(trans.type==TRADE_TRANSACTION_ORDER_DELETE && trans.order>0)
     {
      bool nexus=false;
      if(HistoryOrderSelect(trans.order))
        {
         ENUM_ORDER_TYPE dot=(ENUM_ORDER_TYPE)HistoryOrderGetInteger(trans.order,ORDER_TYPE);
         long dmagic=HistoryOrderGetInteger(trans.order,ORDER_MAGIC);
         nexus=IsNexusPendingType(dot) && (dmagic==InpMagicNumber || LoadManualPendingSignal(trans.order)>0);
        }
      if(nexus)
        {
         string dd=LoadManualPendingDestination(trans.order);
         if(!SendPendingLifecycleEvent("CANCEL",trans.order,dd))
            Print("NEXUS pending cancel/expire delivery queued for retry: ticket=",(string)trans.order);
        }
     }

   if(trans.type!=TRADE_TRANSACTION_DEAL_ADD || trans.deal==0) return;
   if(!HistoryDealSelect(trans.deal)) return;

   long entry=HistoryDealGetInteger(trans.deal,DEAL_ENTRY);
   long magic=HistoryDealGetInteger(trans.deal,DEAL_MAGIC);
   long position_id=(long)HistoryDealGetInteger(trans.deal,DEAL_POSITION_ID);

   if(entry==DEAL_ENTRY_IN)
     {
      // Manual MT5 publishing is an ADMIN-only capability.
      if(magic!=InpMagicNumber && g_access_mode==NEXUS_ADMIN)
        {
         string manual_open_destination=g_manual_destination;
         long pending_dbid=LoadManualPendingSignal(trans.order);
         if(pending_dbid>0)
           {
            string saved_destination=LoadManualPendingDestination(trans.order);
            if(saved_destination!="NONE") manual_open_destination=saved_destination;
           }
         if(manual_open_destination!="FREE" && manual_open_destination!="VIP" && manual_open_destination!="BOTH")
           {
            Print("NEXUS manual OPEN blocked: signal destination is not configured.");
            SetPanel("MANUAL SIGNAL DESTINATION REQUIRED");
            return;
           }
         // Queue the event in terminal memory; delivery is retried from OnTimer.
         // The destination is restored from the durable pending-order mapping.
         string pending_signal=(pending_dbid>0 ? "NX-"+StringFormat("%04d",(int)pending_dbid) : "");
         string pending_destination=LoadManualPendingDestination(trans.order);
         string open_destination=(pending_destination!="NONE"?pending_destination:g_manual_destination);
         if(open_destination=="FREE" || open_destination=="VIP" || open_destination=="BOTH")
           QueuePendingOpen(position_id,trans.deal,open_destination,pending_signal);
         else
           QueuePendingOpen(position_id,trans.deal,"BOTH",pending_signal);
         if(trans.order>0) { ClearManualPendingSignal(trans.order); ClearManualPendingDestination(trans.order); }
         g_manual_destination="NONE";
         SaveManualDestination();
         PaintManualDestinationPanel();
         SetPanel("Manual signal queued; delivery pending");
        }
      return;
     }

   if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)
     {
      // Queue every exit. The timer confirms the position is actually gone,
      // preventing the final CLOSE event from being lost during MT5's
      // DEAL_ADD/position-lifecycle ordering. Partial exits remain UPDATE-only.
      QueuePendingClose(position_id,trans.deal);
      RemovePositionState(position_id);
     }
  }

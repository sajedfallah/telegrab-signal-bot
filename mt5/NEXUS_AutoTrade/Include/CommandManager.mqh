#ifndef NEXUS_COMMAND_MANAGER_MQH
#define NEXUS_COMMAND_MANAGER_MQH

#include "TradeManager.mqh"
#include "APIClient.mqh"
#include "NexusTypes.mqh"

class CNexusCommandManager
  {
private:
   CNexusTradeManager *m_tm;
   CNexusAPIClient *m_api;

   string Prefix(const string signal_id)
     {
      string s=signal_id; StringReplace(s," ","_");
      return "NXS."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"."+s+".";
     }
   void S(const string sig,const string field,const double value) { GlobalVariableSet(Prefix(sig)+field,value); }


   void ApplyModeDefaults(const string sig,const int mode)
     {
      // Server sends a profile code on ACTIVATE_TRAILING. These values are safe
      // v1 fallbacks; the original signal snapshot remains authoritative when present.
      if(mode==1) { S(sig,"break_even_r",1.0); S(sig,"trail_step_r",0.50); S(sig,"lock_step_r",0.30); }
      else if(mode==3) { S(sig,"activation_r",1.0); S(sig,"atr_period",14); S(sig,"atr_multiplier",2.0); }
      else if(mode==4) { S(sig,"activation_r",1.0); S(sig,"swing_left",2); S(sig,"swing_right",2); }
      else if(mode==5) { S(sig,"tp1_close_pct",30); S(sig,"tp2_close_pct",30); S(sig,"runner_pct",40); S(sig,"atr_period",14); S(sig,"atr_multiplier",2.0); S(sig,"swing_left",2); S(sig,"swing_right",2); }
      else if(mode==6) { S(sig,"break_even_r",0.50); S(sig,"trail_step_r",0.35); S(sig,"lock_step_r",0.25); }
      else if(mode==7) { S(sig,"break_even_r",1.0); S(sig,"tp1_close_pct",30); S(sig,"tp2_close_pct",30); S(sig,"runner_pct",40); S(sig,"atr_period",14); S(sig,"atr_multiplier",2.0); S(sig,"swing_left",2); S(sig,"swing_right",2); }
     }

   bool BreakEven(const string sig,string &err)
     {
      ulong ticket=m_tm.FindTicket(sig);
      if(ticket==0 || !PositionSelectByTicket(ticket)) { err="position not found"; return false; }
      double entry=PositionGetDouble(POSITION_PRICE_OPEN);
      if(!m_tm.ModifySL(ticket,entry)) { err=m_tm.LastError(); return false; }
      S(sig,"be_done",1); return true;
     }

   bool UpdateTP(const string sig,const string value,string &err)
     {
      int eq=StringFind(value,"=");
      if(eq<0) { err="invalid TP payload"; return false; }
      string key=NexusTrim(StringSubstr(value,0,eq)); StringToLower(key);
      double price=StringToDouble(NexusTrim(StringSubstr(value,eq+1)));
      if(price<=0) { err="invalid TP price"; return false; }
      if(key=="tp1") { S(sig,"tp1",price); S(sig,"has_tp1",1); }
      else if(key=="tp2") { S(sig,"tp2",price); S(sig,"has_tp2",1); }
      else if(key=="tp3") { S(sig,"tp3",price); S(sig,"has_tp3",1); }
      else if(key=="tp4") { S(sig,"tp4",price); S(sig,"has_tp4",1); }
      else if(key=="tp5") { S(sig,"tp5",price); S(sig,"has_tp5",1); }
      else if(key=="tp6") { S(sig,"tp6",price); S(sig,"has_tp6",1); }
      else if(key=="tp7") { S(sig,"tp7",price); S(sig,"has_tp7",1); }
      else if(key=="tp8") { S(sig,"tp8",price); S(sig,"has_tp8",1); }
      else if(key=="tp9") { S(sig,"tp9",price); S(sig,"has_tp9",1); }
      else if(key=="tp10") { S(sig,"tp10",price); S(sig,"has_tp10",1); }
      else { err="unknown TP target"; return false; }
      int mode=(int)GlobalVariableGet(Prefix(sig)+"mode");
      if(mode==5 || mode==7) return true; // runner profiles use targets as internal thresholds.
      ulong ticket=m_tm.FindTicket(sig);
      if(ticket==0) { err="position not found"; return false; }
      // Hard TP is always the highest numbered available target for non-runner modes.
      double hard=0;
      for(int i=10;i>=1;i--)
        {
         string h=Prefix(sig)+"has_tp"+(string)i;
         if(GlobalVariableCheck(h) && GlobalVariableGet(h)>0.5)
           { hard=GlobalVariableGet(Prefix(sig)+"tp"+(string)i); break; }
        }
      if(!m_tm.ModifyTP(ticket,hard)) { err=m_tm.LastError(); return false; }
      return true;
     }

public:
   CNexusCommandManager():m_tm(NULL),m_api(NULL) {}
   void Configure(CNexusTradeManager *tm,CNexusAPIClient *api) { m_tm=tm; m_api=api; }

   bool Execute(const NexusCommand &c,string &err)
     {
      err="";
      if(m_tm==NULL) { err="trade manager unavailable"; return false; }
      if(c.command=="MOVE_SL_TO_ENTRY") return BreakEven(c.signal_id,err);
      if(c.command=="PARTIAL_CLOSE")
        {
         double pct=StringToDouble(c.payload_value);
         if(pct<=0 || pct>=100) { err="partial percentage must be >0 and <100"; return false; }
         if(!m_tm.PartialClosePercent(c.signal_id,pct)) { err=m_tm.LastError(); return false; }
         return true;
        }
      if(c.command=="UPDATE_SL")
        {
         double sl=StringToDouble(c.payload_value);
         ulong ticket=m_tm.FindTicket(c.signal_id);
         if(ticket==0 || sl<=0) { err="invalid SL/position"; return false; }
         if(!m_tm.ModifySL(ticket,sl)) { err=m_tm.LastError(); return false; }
         return true;
        }
      if(c.command=="UPDATE_TP") return UpdateTP(c.signal_id,c.payload_value,err);
      if(c.command=="ACTIVATE_TRAILING")
        {
         string trail_code=c.payload_value; StringToUpper(trail_code); int mode=NexusTrailingModeNumber(trail_code);
         if(mode==0) { err="unsupported trailing profile"; return false; }
         if(m_tm.FindTicket(c.signal_id)==0) { err="position not found"; return false; }
         S(c.signal_id,"mode",mode); ApplyModeDefaults(c.signal_id,mode); return true;
        }
      if(c.command=="CLOSE_SIGNAL")
        {
         if(!m_tm.CloseSignal(c.signal_id)) { err=m_tm.LastError(); return false; }
         return true;
        }
      err="unsupported command: "+c.command;
      return false;
     }
  };

#endif

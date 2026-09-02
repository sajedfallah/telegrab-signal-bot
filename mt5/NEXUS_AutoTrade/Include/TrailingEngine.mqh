#ifndef NEXUS_TRAILING_ENGINE_MQH
#define NEXUS_TRAILING_ENGINE_MQH

#include "TradeManager.mqh"

// File-scope helpers intentionally avoid static/private member lookup issues
// in some MetaEditor parser builds. They are pure account-scoped state accessors.
string NexusTrailPrefix(const string sig)
  {
   string s=sig;
   StringReplace(s," ","_");
   StringReplace(s,"/","_");
   return "NXS."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"."+s+".";
  }

double NexusTrailGet(const string sig,const string field,const double def=0)
  {
   string k=NexusTrailPrefix(sig)+field;
   return GlobalVariableCheck(k)?GlobalVariableGet(k):def;
  }

void NexusTrailSet(const string sig,const string field,const double v)
  {
   GlobalVariableSet(NexusTrailPrefix(sig)+field,v);
  }

// Hardened profile-based trailing engine.
// NEXUS positions use the immutable signal snapshot.
// Manual positions are managed only with explicit EA opt-in and use
// their own Entry / Initial SL / Final TP as source of truth.
class CNexusTrailingEngine
  {
private:
   CNexusTradeManager *m_tm;
   long m_magic;
   ENUM_TIMEFRAMES m_tf;

   double Price(const string symbol,const ENUM_POSITION_TYPE pt)
     { return pt==POSITION_TYPE_BUY?SymbolInfoDouble(symbol,SYMBOL_BID):SymbolInfoDouble(symbol,SYMBOL_ASK); }
   bool Better(const ENUM_POSITION_TYPE pt,const double oldsl,const double newsl)
     { if(newsl<=0||!MathIsValidNumber(newsl)) return false; if(oldsl==0) return true; return pt==POSITION_TYPE_BUY?newsl>oldsl:newsl<oldsl; }
   double Clamp(const string symbol,const ENUM_POSITION_TYPE pt,double sl)
     {
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT); if(point<=0) return 0;
      int stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
      int freeze=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
      double dist=MathMax(1,MathMax(stops,freeze))*point, px=Price(symbol,pt);
      sl=(pt==POSITION_TYPE_BUY?MathMin(sl,px-dist):MathMax(sl,px+dist));
      return NormalizeDouble(sl,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS));
     }
   bool MoveSL(const ulong ticket,const ENUM_POSITION_TYPE pt,const double proposed)
     {
      if(m_tm==NULL||!PositionSelectByTicket(ticket)) return false;
      string symbol=PositionGetString(POSITION_SYMBOL); double oldsl=PositionGetDouble(POSITION_SL); double sl=Clamp(symbol,pt,proposed);
      if(!Better(pt,oldsl,sl)) return false; return m_tm.ModifySL(ticket,sl);
     }
   ENUM_TIMEFRAMES SignalTF(const string sig)
     {
      int tf=(int)NexusTrailGet(sig,"timeframe_code",(double)m_tf);
      switch(tf)
        {
         case PERIOD_M1: return PERIOD_M1; case PERIOD_M3: return PERIOD_M3; case PERIOD_M5: return PERIOD_M5;
         case PERIOD_M15: return PERIOD_M15; case PERIOD_M30: return PERIOD_M30; case PERIOD_H1: return PERIOD_H1;
         case PERIOD_H4: return PERIOD_H4; case PERIOD_D1: return PERIOD_D1; case PERIOD_W1: return PERIOD_W1;
        }
      return m_tf;
     }

   double ATR(const string symbol,const int period)
     {
      int h=iATR(symbol,m_tf,MathMax(2,period)); if(h==INVALID_HANDLE) return 0;
      double b[]; ArraySetAsSeries(b,true); double v=0; if(CopyBuffer(h,0,1,1,b)==1) v=b[0]; IndicatorRelease(h); return v;
     }
   double Swing(const string symbol,const ENUM_POSITION_TYPE pt,const int left,const int right)
     {
      int need=MathMax(30,left+right+10); MqlRates r[]; ArraySetAsSeries(r,true); int n=CopyRates(symbol,m_tf,1,need,r); if(n<=left+right+1) return 0;
      for(int i=right;i<n-left;i++)
        {
         bool ok=true; double v=pt==POSITION_TYPE_BUY?r[i].low:r[i].high;
         for(int j=1;j<=left;j++) { if(pt==POSITION_TYPE_BUY&&r[i+j].low<=v)ok=false; if(pt==POSITION_TYPE_SELL&&r[i+j].high>=v)ok=false; }
         for(int j=1;j<=right;j++) { if(pt==POSITION_TYPE_BUY&&r[i-j].low<=v)ok=false; if(pt==POSITION_TYPE_SELL&&r[i-j].high>=v)ok=false; }
         if(ok)return v;
        }
      return 0;
     }
   double R(const ENUM_POSITION_TYPE pt,const double px,const double entry,const double risk)
     { return risk>0?(pt==POSITION_TYPE_BUY?(px-entry)/risk:(entry-px)/risk):0; }
   double AtR(const ENUM_POSITION_TYPE pt,const double entry,const double risk,const double lock)
     { return pt==POSITION_TYPE_BUY?entry+lock*risk:entry-lock*risk; }
   void BE(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,const double entry)
     {
      if(NexusTrailGet(sig,"be_done",0)>0.5)return;
      if(!PositionSelectByTicket(ticket))return;
      string symbol=PositionGetString(POSITION_SYMBOL);
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      double px=Price(symbol,pt);
      int stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
      int freeze=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
      double dist=MathMax(1,MathMax(stops,freeze))*point;
      if((pt==POSITION_TYPE_BUY && px-entry<dist) || (pt==POSITION_TYPE_SELL && entry-px<dist)) return;
      if(!MoveSL(ticket,pt,entry)) return;
      if(PositionSelectByTicket(ticket))
        {
         double actual=PositionGetDouble(POSITION_SL);
         if((pt==POSITION_TYPE_BUY && actual>=entry-point*0.1) || (pt==POSITION_TYPE_SELL && actual<=entry+point*0.1)) NexusTrailSet(sig,"be_done",1);
        }
     }

   void Step(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,const double entry,const double risk,const double pr,const double trigger,const double step,const double lock)
     {
      if(pr<trigger)return; BE(ticket,sig,pt,entry); if(step<=0||lock<=0)return;
      int levels=(int)MathFloor((pr-trigger)/step)+1; MoveSL(ticket,pt,AtR(pt,entry,risk,levels*lock));
     }
   void ATRTrail(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,const string symbol,const double pr)
     {
      if(pr<NexusTrailGet(sig,"activation_r",1))return; double a=ATR(symbol,(int)NexusTrailGet(sig,"atr_period",14)); if(a<=0)return;
      double px=Price(symbol,pt), mult=NexusTrailGet(sig,"atr_multiplier",2); MoveSL(ticket,pt,pt==POSITION_TYPE_BUY?px-a*mult:px+a*mult);
     }
   void StructureTrail(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,const string symbol,const double pr)
     {
      if(pr<NexusTrailGet(sig,"activation_r",1))return; double sw=Swing(symbol,pt,(int)NexusTrailGet(sig,"swing_left",2),(int)NexusTrailGet(sig,"swing_right",2)); if(sw>0)MoveSL(ticket,pt,sw);
     }

   double Target(const string sig,const int n)
     {
      if(n<1||n>10)return 0;
      return NexusTrailGet(sig,"tp"+IntegerToString(n),0);
     }
   bool TargetEnabled(const string sig,const int n)
     {
      if(n<1||n>10)return false;
      return NexusTrailGet(sig,"has_tp"+IntegerToString(n),0)>0.5 && Target(sig,n)>0;
     }
   int TargetCount(const string sig)
     {
      int count=0;
      for(int n=1;n<=10;n++) if(TargetEnabled(sig,n)) count=n;
      return count;
     }
   double TargetClosePct(const string sig,const int n,const int count)
     {
      // Preserve the legacy 2-target profile (30% / 30% / runner 40%).
      // With 3 targets the first two are partials and TP3 is the final exit.
      // With 4+ targets, distribute 100% evenly across the target ladder;
      // the last target closes the remaining volume.
      if(n>=count)return 100.0;
      if(count==2)return n==1?NexusTrailGet(sig,"tp1_close_pct",30):30.0;
      if(count==3)return 30.0;
      return 100.0/MathMax(1,count);
     }
   bool PartialRetryReady(const string sig,const int n)
     {
      return TimeCurrent()>=(datetime)NexusTrailGet(sig,"tp"+IntegerToString(n)+"_next_retry",0);
     }

   void PartialRetrySchedule(const string sig,const int n,const string reason)
     {
      string p="tp"+IntegerToString(n);
      int attempts=(int)NexusTrailGet(sig,p+"_attempts",0)+1;
      NexusTrailSet(sig,p+"_attempts",attempts);
      // Bounded exponential backoff: 1,2,4,8,16,30,30...
      int delay=(int)MathMin(30.0,MathPow(2.0,MathMin(attempts-1,5)));
      NexusTrailSet(sig,p+"_next_retry",(double)(TimeCurrent()+delay));
      Print("NEXUS TP PARTIAL RETRY | signal=",sig," tp=",(string)n,
            " attempt=",(string)attempts," next_in=",(string)delay,"s reason=",reason);
     }

   void PartialRetryReset(const string sig,const int n)
     {
      string p="tp"+IntegerToString(n);
      NexusTrailSet(sig,p+"_attempts",0);
      NexusTrailSet(sig,p+"_next_retry",0);
     }


   void Partials(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,const double px,const double entry,const double risk)
     {
      if(!PositionSelectByTicket(ticket))return;
      int count=TargetCount(sig);
      double initv=NexusTrailGet(sig,"initial_volume",PositionGetDouble(POSITION_VOLUME)); if(initv<=0)return;

      // Manual positions may not carry explicit target levels. Preserve the
      // existing fallback behaviour by deriving two R-based milestones from
      // the final broker TP when necessary.
      if(NexusTrailGet(sig,"manual",0)>0.5 && count==0)
        {
         double finaltp=NexusTrailGet(sig,"final_tp",0); if(finaltp<=0||risk<=0)return;
         double d=pt==POSITION_TYPE_BUY?1.0:-1.0;
         double tp1=entry+d*risk, tp2=entry+d*2*risk;
         if((pt==POSITION_TYPE_BUY && tp1<finaltp)||(pt==POSITION_TYPE_SELL && tp1>finaltp)) { NexusTrailSet(sig,"tp1",tp1); NexusTrailSet(sig,"has_tp1",1); }
         if((pt==POSITION_TYPE_BUY && tp2<finaltp)||(pt==POSITION_TYPE_SELL && tp2>finaltp)) { NexusTrailSet(sig,"tp2",tp2); NexusTrailSet(sig,"has_tp2",1); }
         count=TargetCount(sig);
         if(count<=0)return;
        }

      for(int n=1;n<=count;n++)
        {
         string field="tp"+IntegerToString(n);
         if(NexusTrailGet(sig,field+"_done",0)>0.5) continue;
         if(!PartialRetryReady(sig,n)) continue;
         double target=Target(sig,n);
         if(target<=0) continue;
         bool hit=pt==POSITION_TYPE_BUY?px>=target:px<=target;
         if(!hit) continue;

         bool is_final_target=(n==count);
         double close_pct=TargetClosePct(sig,n,count);
         double before=PositionGetDouble(POSITION_VOLUME);
         double close_volume=is_final_target?before:initv*close_pct/100.0;
         if(close_volume<=0) continue;

         Print("NEXUS TP HIT | signal=",sig," tp=",(string)n,
               " target=",DoubleToString(target,8)," before_volume=",DoubleToString(before,8),
               " requested_close_pct=",DoubleToString(close_pct,2)," requested_close=",DoubleToString(close_volume,8));

         if(!m_tm.PartialCloseVolume(ticket,close_volume))
           {
            PartialRetrySchedule(sig,n,m_tm.LastError());
            continue;
           }

         NexusTrailSet(sig,field+"_done",1);
         PartialRetryReset(sig,n);

         // Target completion is a state transition. The target anchor is
         // applied only after execution is confirmed, never before.
         if(n==1) BE(ticket,sig,pt,entry);
         else if(PositionSelectByTicket(ticket)) MoveSL(ticket,pt,Target(sig,n-1));
         if(is_final_target) NexusTrailSet(sig,"final_tp_done",1);
         Print("NEXUS TP COMPLETED | signal=",sig," tp=",(string)n,
               " final=",is_final_target?"YES":"NO");

         if(is_final_target || !PositionSelectByTicket(ticket)) return;
        }
     }

   int Mode(const string code)
     { int m=NexusTrailingModeNumber(code); return m>=1&&m<=7?m:7; }
   void ManualProfile(const string sig,const string code)
     {
      int m=Mode(code); NexusTrailSet(sig,"profile_mode",m);
      if(m==1){NexusTrailSet(sig,"profile_be",1);NexusTrailSet(sig,"profile_step",.50);NexusTrailSet(sig,"profile_lock",.30);}
      else if(m==2){NexusTrailSet(sig,"profile_be",1);}
      else if(m==3){NexusTrailSet(sig,"profile_activation",1);NexusTrailSet(sig,"profile_atr_period",14);NexusTrailSet(sig,"profile_atr_multiplier",2);}
      else if(m==4){NexusTrailSet(sig,"profile_activation",1);NexusTrailSet(sig,"profile_swing_left",2);NexusTrailSet(sig,"profile_swing_right",2);}
      else if(m==5){NexusTrailSet(sig,"profile_tp1_pct",30);NexusTrailSet(sig,"profile_tp2_pct",30);NexusTrailSet(sig,"profile_activation",1);NexusTrailSet(sig,"profile_atr_period",14);NexusTrailSet(sig,"profile_atr_multiplier",2);NexusTrailSet(sig,"profile_swing_left",2);NexusTrailSet(sig,"profile_swing_right",2);}
      else if(m==6){NexusTrailSet(sig,"profile_be",.50);NexusTrailSet(sig,"profile_step",.35);NexusTrailSet(sig,"profile_lock",.25);}
      else {NexusTrailSet(sig,"profile_be",1);NexusTrailSet(sig,"profile_tp1_pct",30);NexusTrailSet(sig,"profile_tp2_pct",30);NexusTrailSet(sig,"profile_activation",1);NexusTrailSet(sig,"profile_atr_period",14);NexusTrailSet(sig,"profile_atr_multiplier",2);NexusTrailSet(sig,"profile_swing_left",2);NexusTrailSet(sig,"profile_swing_right",2);}
     }
   void InitManual(const ulong ticket,const long identifier,const string sig,const string code)
     {
      if(NexusTrailGet(sig,"initialized",0)>0.5)return; if(!PositionSelectByTicket(ticket))return;
      double e=PositionGetDouble(POSITION_PRICE_OPEN),sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP),v=PositionGetDouble(POSITION_VOLUME);
      ENUM_POSITION_TYPE pt=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      // Safety gate: an invalid manual SL or a TP on the wrong side is never
      // allowed to become the basis of automatic management.
      if(e<=0||sl<=0||v<=0)return;
      if(pt==POSITION_TYPE_BUY && sl>=e)return;
      if(pt==POSITION_TYPE_SELL && sl<=e)return;
      if(tp>0 && ((pt==POSITION_TYPE_BUY && tp<=e)||(pt==POSITION_TYPE_SELL && tp>=e))) tp=0;
      ManualProfile(sig,code); int m=(int)NexusTrailGet(sig,"profile_mode",7);
      NexusTrailSet(sig,"initialized",1);NexusTrailSet(sig,"manual",1);NexusTrailSet(sig,"identifier",(double)identifier);NexusTrailSet(sig,"mode",m);NexusTrailSet(sig,"initial_sl",sl);NexusTrailSet(sig,"signal_entry",e);NexusTrailSet(sig,"final_tp",tp);NexusTrailSet(sig,"initial_volume",v);
      NexusTrailSet(sig,"be_done",0);NexusTrailSet(sig,"tp1_done",0);NexusTrailSet(sig,"tp2_done",0);NexusTrailSet(sig,"has_tp1",0);NexusTrailSet(sig,"has_tp2",0);
      NexusTrailSet(sig,"break_even_r",NexusTrailGet(sig,"profile_be",1));NexusTrailSet(sig,"trail_step_r",NexusTrailGet(sig,"profile_step",.35));NexusTrailSet(sig,"lock_step_r",NexusTrailGet(sig,"profile_lock",.25));
      NexusTrailSet(sig,"activation_r",NexusTrailGet(sig,"profile_activation",1));NexusTrailSet(sig,"atr_period",NexusTrailGet(sig,"profile_atr_period",14));NexusTrailSet(sig,"atr_multiplier",NexusTrailGet(sig,"profile_atr_multiplier",2));
      NexusTrailSet(sig,"swing_left",NexusTrailGet(sig,"profile_swing_left",2));NexusTrailSet(sig,"swing_right",NexusTrailGet(sig,"profile_swing_right",2));NexusTrailSet(sig,"tp1_close_pct",NexusTrailGet(sig,"profile_tp1_pct",30));NexusTrailSet(sig,"tp2_close_pct",NexusTrailGet(sig,"profile_tp2_pct",30));
     }

public:
   CNexusTrailingEngine():m_tm(NULL),m_magic(258025),m_tf(PERIOD_M1){}
   void Configure(CNexusTradeManager *tm,const long magic,const ENUM_TIMEFRAMES tf){m_tm=tm;m_magic=magic;m_tf=tf;}

   void ManageAll(const bool manage_manual=false,const string manual_profile="NEXUS_TRAIL_07")
     {
      if(m_tm==NULL)return;
      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong ticket=PositionGetTicket(i); if(ticket==0||!PositionSelectByTicket(ticket))continue;
         long magic=(long)PositionGetInteger(POSITION_MAGIC); bool nexus=magic==m_magic; bool manual=!nexus&&manage_manual; if(!nexus&&!manual)continue;
         string sig=PositionGetString(POSITION_COMMENT); long id=(long)PositionGetInteger(POSITION_IDENTIFIER);
         if(manual){sig="MANUAL."+(string)id;InitManual(ticket,id,sig,manual_profile);} else if(sig=="")continue;
         int mode=(int)NexusTrailGet(sig,"mode",0); if(mode<1||mode>7)continue;
         m_tf=SignalTF(sig);
         string symbol=PositionGetString(POSITION_SYMBOL); ENUM_POSITION_TYPE pt=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE); double entry=PositionGetDouble(POSITION_PRICE_OPEN);
         datetime now=TimeCurrent();
         if(now<=NexusTrailGet(sig,"trail_last_sec",0)) continue;
         NexusTrailSet(sig,"trail_last_sec",(double)now);
         double risk=MathAbs(entry-NexusTrailGet(sig,"initial_sl",PositionGetDouble(POSITION_SL))); if(risk<=0)continue; double pr=R(pt,Price(symbol,pt),entry,risk);
         if(mode==1)
            Step(ticket,sig,pt,entry,risk,pr,NexusTrailGet(sig,"break_even_r",1),NexusTrailGet(sig,"trail_step_r",.5),NexusTrailGet(sig,"lock_step_r",.3));
         else if(mode==2)
           {
            // Fixed R milestones from the immutable initial risk. Each level
            // is monotonic; no stop can ever move backward.
            if(pr>=3.0) MoveSL(ticket,pt,AtR(pt,entry,risk,2.0));
            else if(pr>=2.0) MoveSL(ticket,pt,AtR(pt,entry,risk,1.0));
            else if(pr>=1.0) BE(ticket,sig,pt,entry);
           }
         else if(mode==3)
            ATRTrail(ticket,sig,pt,symbol,pr);
         else if(mode==4)
            StructureTrail(ticket,sig,pt,symbol,pr);
         else if(mode==5)
           {
            // TP execution is confirmed before any runner trail is allowed to
            // react to the newly reached target.
            Partials(ticket,sig,pt,Price(symbol,pt),entry,risk);
            if(PositionSelectByTicket(ticket))
              {
               double runner_pr=R(pt,Price(symbol,pt),entry,risk);
               StructureTrail(ticket,sig,pt,symbol,runner_pr);
               ATRTrail(ticket,sig,pt,symbol,runner_pr);
              }
           }
         else if(mode==6)
            Step(ticket,sig,pt,entry,risk,pr,NexusTrailGet(sig,"break_even_r",.5),NexusTrailGet(sig,"trail_step_r",.35),NexusTrailGet(sig,"lock_step_r",.25));
         else
           {
            if(pr>=NexusTrailGet(sig,"break_even_r",1)) BE(ticket,sig,pt,entry);
            Partials(ticket,sig,pt,Price(symbol,pt),entry,risk);
            if(PositionSelectByTicket(ticket))
              {
               // Structure and ATR are runner-only. They never get a chance to
               // falsely mark a target as complete and they remain monotonic.
               double runner_pr=R(pt,Price(symbol,pt),entry,risk);
               StructureTrail(ticket,sig,pt,symbol,runner_pr);
               ATRTrail(ticket,sig,pt,symbol,runner_pr);
              }
           }
        }
     }
  };
#endif

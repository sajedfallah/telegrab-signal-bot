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

// Legacy helper retained for backwards source compatibility and old state.
bool NexusTrailClaimManageSecond(const string sig,const datetime now)
  {
   string key=NexusTrailPrefix(sig)+"trail_last_sec";
   if(!GlobalVariableCheck(key)) GlobalVariableSet(key,0.0);
   double previous=GlobalVariableGet(key);
   if((double)now<=previous) return false;
   return GlobalVariableSetOnCondition(key,(double)now,previous);
  }

// V35: use the broker tick timestamp rather than a one-second gate. This keeps
// multi-chart ownership atomic while preventing a fast TP touch from being
// ignored simply because another chart instance managed the same signal earlier
// in the current second. Millisecond Unix timestamps are exactly representable
// in an MQL double at present-day magnitudes.
bool NexusTrailClaimManageTick(const string sig,const long tick_msc)
  {
   if(tick_msc<=0) return false;
   string key=NexusTrailPrefix(sig)+"trail_last_tick_msc";
   if(!GlobalVariableCheck(key)) GlobalVariableSet(key,0.0);
   double previous=GlobalVariableGet(key);
   if((double)tick_msc<=previous) return false;
   return GlobalVariableSetOnCondition(key,(double)tick_msc,previous);
  }

string NexusTrailSignalForTicket(const ulong ticket,const string broker_comment)
  {
   string sig=broker_comment;
   StringTrimLeft(sig); StringTrimRight(sig);
   if(sig!="" && NexusTrailGet(sig,"mode",0)>=1) return sig;

   // A broker may erase POSITION_COMMENT after a partial close. Recover the
   // signal from the account-scoped ticket already persisted by TradeManager.
   string prefix="NXS."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+".";
   string suffix=".ticket";
   for(int i=0;i<GlobalVariablesTotal();i++)
     {
      string key=GlobalVariableName(i);
      if(StringFind(key,prefix)!=0) continue;
      int at=StringLen(key)-StringLen(suffix);
      if(at<=StringLen(prefix) || StringSubstr(key,at)!=suffix) continue;
      if((ulong)MathRound(GlobalVariableGet(key))!=ticket) continue;
      sig=StringSubstr(key,StringLen(prefix),at-StringLen(prefix));
      if(NexusTrailGet(sig,"mode",0)>=1) return sig;
     }
   return "";
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
   ENUM_TIMEFRAMES m_default_tf;

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
      int tf=(int)NexusTrailGet(sig,"timeframe_code",(double)m_default_tf);
      switch(tf)
        {
         case PERIOD_M1: return PERIOD_M1; case PERIOD_M3: return PERIOD_M3; case PERIOD_M5: return PERIOD_M5;
         case PERIOD_M15: return PERIOD_M15; case PERIOD_M30: return PERIOD_M30; case PERIOD_H1: return PERIOD_H1;
         case PERIOD_H4: return PERIOD_H4; case PERIOD_D1: return PERIOD_D1; case PERIOD_W1: return PERIOD_W1;
        }
      return m_default_tf;
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
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT); if(point<=0)return;
      double current_sl=PositionGetDouble(POSITION_SL);
      // A manual/previous milestone may already have protected entry or better.
      // Reconcile state instead of retrying an impossible non-improving move.
      if(current_sl>0 && ((pt==POSITION_TYPE_BUY && current_sl>=entry-point*0.1) ||
                          (pt==POSITION_TYPE_SELL && current_sl<=entry+point*0.1)))
        { NexusTrailSet(sig,"be_done",1); return; }
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
      if(pr<trigger)return;
      BE(ticket,sig,pt,entry);
      if(step<=0||lock<=0)return;
      // Trigger itself is Break Even. Profit locking starts only after one
      // complete step beyond the trigger: e.g. T01 1R=BE, 1.5R=+0.3R.
      int levels=(int)MathFloor((pr-trigger)/step);
      if(levels<=0)return;
      MoveSL(ticket,pt,AtR(pt,entry,risk,levels*lock));
     }
   void ATRTrail(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,const string symbol,const double pr)
     {
      if(pr<NexusTrailGet(sig,"activation_r",1))return; double a=ATR(symbol,(int)NexusTrailGet(sig,"atr_period",14)); if(a<=0)return;
      double px=Price(symbol,pt), mult=NexusTrailGet(sig,"atr_multiplier",2); MoveSL(ticket,pt,pt==POSITION_TYPE_BUY?px-a*mult:px+a*mult);
     }
   bool StructureTrail(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,const string symbol,const double pr)
     {
      if(pr<NexusTrailGet(sig,"activation_r",1))return false;
      double sw=Swing(symbol,pt,(int)NexusTrailGet(sig,"swing_left",2),(int)NexusTrailGet(sig,"swing_right",2));
      if(sw<=0)return false;
      // A valid market structure exists even when the current SL is already
      // tighter. ATR is a true fallback only when no valid structure exists.
      MoveSL(ticket,pt,sw);
      return true;
     }
   void RunnerTrail(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,const string symbol,const double pr)
     {
      if(!StructureTrail(ticket,sig,pt,symbol,pr))
         ATRTrail(ticket,sig,pt,symbol,pr);
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
      // T05/T07 contract: percentages are shares of ORIGINAL volume.
      // TP1 closes configured first share; TP2 closes configured second share
      // when a later final target exists; intermediate targets are milestones;
      // the final target always closes the entire remaining runner.
      if(count<=0||n<1)return 0.0;
      if(n>=count)return 100.0;
      double runner=MathMax(0.0,MathMin(100.0,NexusTrailGet(sig,"runner_pct",40)));
      double first=MathMax(0.0,MathMin(100.0-runner,NexusTrailGet(sig,"tp1_close_pct",30)));
      if(n==1)return first;
      if(n==2 && count>=3)
         return MathMax(0.0,MathMin(100.0-runner-first,NexusTrailGet(sig,"tp2_close_pct",30)));
      return 0.0;
     }

   double ExecutablePartialVolume(const string symbol,const double before,const double requested,const double reserve)
     {
      double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      if(minv<=0 || before<=0)return -1;
      if(requested<=0)return 0;
      if(step<=0)step=minv;
      double eps=MathMax(step*0.1,1e-8);
      double max_partial=before-MathMax(minv,reserve);
      if(max_partial+eps<minv)return 0;
      double volume=NormalizeDouble(MathRound(requested/step)*step,8);
      if(volume<minv)volume=minv;
      if(volume>max_partial)volume=MathFloor(max_partial/step+1e-9)*step;
      volume=NormalizeDouble(volume,8);
      if(volume<minv || before-volume+eps<minv)return 0;
      return volume;
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

   void SavePartialTruth(const string sig,const int n,const double initial,const double before,const double after)
     {
      string p="tp"+IntegerToString(n);
      double closed=MathMax(0.0,before-after);
      NexusTrailSet(sig,p+"_closed_volume",closed);
      NexusTrailSet(sig,p+"_remaining_volume",MathMax(0.0,after));
      NexusTrailSet(sig,p+"_closed_pct_actual",initial>0?closed/initial*100.0:0.0);
      NexusTrailSet(sig,p+"_remaining_pct_actual",initial>0?MathMax(0.0,after)/initial*100.0:0.0);
     }

   void CompleteTarget(const ulong ticket,const string sig,const ENUM_POSITION_TYPE pt,
                       const double entry,const int n,const bool is_final)
     {
      string field="tp"+IntegerToString(n);
      NexusTrailSet(sig,field+"_done",1);
      PartialRetryReset(sig,n);
      NexusTrailSet(sig,field+"_pending_before",0);
      NexusTrailSet(sig,field+"_pending_volume",0);
      if(n==1) BE(ticket,sig,pt,entry);
      else if(PositionSelectByTicket(ticket)) MoveSL(ticket,pt,Target(sig,n-1));
      if(is_final) NexusTrailSet(sig,"final_tp_done",1);
      GlobalVariablesFlush();
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
         // The broker's final TP is the final milestone, not an early
         // synthetic target that closes the entire manual position.
         int final_index=TargetCount(sig)+1;
         NexusTrailSet(sig,"tp"+IntegerToString(final_index),finaltp);
         NexusTrailSet(sig,"has_tp"+IntegerToString(final_index),1);
         count=TargetCount(sig);
         if(count<=0)return;
        }

      for(int n=1;n<=count;n++)
        {
         string field="tp"+IntegerToString(n);
         if(NexusTrailGet(sig,field+"_done",0)>0.5) continue;

         // V34 and older could permanently mark an impossible broker-grid split
         // as "skipped" after the target was already hit. Reconcile that durable
         // state into a completed milestone so an upgraded live position cannot
         // get stuck forever at the old target.
         if(NexusTrailGet(sig,field+"_skipped",0)>0.5)
           {
            NexusTrailSet(sig,field+"_skipped",0);
            NexusTrailSet(sig,field+"_volume_skipped",1);
            CompleteTarget(ticket,sig,pt,entry,n,n==count);
            Print("NEXUS TP LEGACY SKIP RECONCILED | signal=",sig," tp=",(string)n);
            if(n==count)return;
            continue;
           }

         bool is_final_target=(n==count);
         double pending_before=NexusTrailGet(sig,field+"_pending_before",0);
         if(pending_before>0)
           {
            if(!PositionSelectByTicket(ticket))return;
            double current=PositionGetDouble(POSITION_VOLUME);
            double step=SymbolInfoDouble(PositionGetString(POSITION_SYMBOL),SYMBOL_VOLUME_STEP);
            double threshold=MathMax(step*0.5,1e-8);
            if(current<pending_before-threshold)
              {
               // The previous attempt reduced broker volume before the EA
               // restarted or lost its acknowledgement. Never close twice.
               SavePartialTruth(sig,n,initv,pending_before,current);
               Print("NEXUS TP PARTIAL RECONCILED | signal=",sig," tp=",(string)n,
                     " before=",DoubleToString(pending_before,8),
                     " after=",DoubleToString(current,8));
               CompleteTarget(ticket,sig,pt,entry,n,is_final_target);
               if(is_final_target)return;
               continue;
              }
            if(!PartialRetryReady(sig,n)) continue;
            NexusTrailSet(sig,field+"_pending_before",0);
            NexusTrailSet(sig,field+"_pending_volume",0);
           }
         if(!PartialRetryReady(sig,n)) continue;
         double target=Target(sig,n);
         if(target<=0) continue;
         bool hit=pt==POSITION_TYPE_BUY?px>=target:px<=target;
         if(!hit) continue;

         double close_pct=TargetClosePct(sig,n,count);
         double before=PositionGetDouble(POSITION_VOLUME);

         // Intermediate TP3..TP(n-1) are management milestones in the 30/30/40
         // runner contract. They advance the SL but never consume runner volume.
         if(!is_final_target && close_pct<=0)
           {
            NexusTrailSet(sig,field+"_milestone_only",1);
            CompleteTarget(ticket,sig,pt,entry,n,false);
            Print("NEXUS TP MILESTONE | signal=",sig," tp=",(string)n,
                  " target=",DoubleToString(target,8)," volume_unchanged=",DoubleToString(before,8));
            continue;
           }

         double close_volume=is_final_target?before:initv*close_pct/100.0;
         if(!is_final_target)
           {
            string symbol=PositionGetString(POSITION_SYMBOL);
            double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
            double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
            if(step<=0)step=minv;
            double runner_pct=MathMax(0.0,MathMin(100.0,NexusTrailGet(sig,"runner_pct",40)));
            double reserve=(step>0?MathCeil(initv*runner_pct/100.0/step-1e-9)*step:0);
            close_volume=ExecutablePartialVolume(symbol,before,close_volume,reserve);
            if(close_volume<0)
              {
               PartialRetrySchedule(sig,n,"broker volume metadata unavailable");
               continue;
              }
            if(close_volume<=0)
              {
               // The target really was reached, but broker min/step prevents
               // another legal split while preserving the runner. Complete the
               // target milestone and advance protection; never claim a volume
               // close that did not happen and never retry an impossible split.
               NexusTrailSet(sig,field+"_volume_skipped",1);
               NexusTrailSet(sig,field+"_closed_volume",0);
               NexusTrailSet(sig,field+"_closed_pct_actual",0);
               NexusTrailSet(sig,field+"_remaining_volume",before);
               NexusTrailSet(sig,field+"_remaining_pct_actual",initv>0?before/initv*100.0:0);
               CompleteTarget(ticket,sig,pt,entry,n,false);
               Print("NEXUS TP PARTIAL GRID-SKIPPED | signal=",sig," tp=",(string)n,
                     " before=",DoubleToString(before,8)," initial=",DoubleToString(initv,8),
                     " reason=broker minimum volume/step; milestone completed");
               continue;
              }
           }

         Print("NEXUS TP HIT | signal=",sig," tp=",(string)n,
               " target=",DoubleToString(target,8)," before_volume=",DoubleToString(before,8),
               " requested_close_pct=",DoubleToString(close_pct,2)," requested_close=",DoubleToString(close_volume,8));

         NexusTrailSet(sig,field+"_pending_before",before);
         NexusTrailSet(sig,field+"_pending_volume",close_volume);
         GlobalVariablesFlush();
         if(!m_tm.PartialCloseVolume(ticket,close_volume))
           {
            PartialRetrySchedule(sig,n,m_tm.LastError());
            continue;
           }

         double after=0.0;
         if(PositionSelectByTicket(ticket)) after=PositionGetDouble(POSITION_VOLUME);
         SavePartialTruth(sig,n,initv,before,after);

         // Target completion is a state transition. The target anchor is
         // applied only after execution is confirmed, never before.
         CompleteTarget(ticket,sig,pt,entry,n,is_final_target);
         Print("NEXUS TP COMPLETED | signal=",sig," tp=",(string)n,
               " final=",is_final_target?"YES":"NO",
               " actual_closed=",DoubleToString(NexusTrailGet(sig,field+"_closed_volume",0),8),
               " actual_closed_pct_initial=",DoubleToString(NexusTrailGet(sig,field+"_closed_pct_actual",0),2),
               " remaining=",DoubleToString(NexusTrailGet(sig,field+"_remaining_volume",0),8));

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
      NexusTrailSet(sig,"timeframe_code",(double)m_default_tf);
      NexusTrailSet(sig,"be_done",0);NexusTrailSet(sig,"tp1_done",0);NexusTrailSet(sig,"tp2_done",0);NexusTrailSet(sig,"has_tp1",0);NexusTrailSet(sig,"has_tp2",0);
      NexusTrailSet(sig,"trail_last_sec",0);NexusTrailSet(sig,"trail_last_tick_msc",0);
      NexusTrailSet(sig,"break_even_r",NexusTrailGet(sig,"profile_be",1));NexusTrailSet(sig,"trail_step_r",NexusTrailGet(sig,"profile_step",.35));NexusTrailSet(sig,"lock_step_r",NexusTrailGet(sig,"profile_lock",.25));
      NexusTrailSet(sig,"activation_r",NexusTrailGet(sig,"profile_activation",1));NexusTrailSet(sig,"atr_period",NexusTrailGet(sig,"profile_atr_period",14));NexusTrailSet(sig,"atr_multiplier",NexusTrailGet(sig,"profile_atr_multiplier",2));
      NexusTrailSet(sig,"swing_left",NexusTrailGet(sig,"profile_swing_left",2));NexusTrailSet(sig,"swing_right",NexusTrailGet(sig,"profile_swing_right",2));NexusTrailSet(sig,"tp1_close_pct",NexusTrailGet(sig,"profile_tp1_pct",30));NexusTrailSet(sig,"tp2_close_pct",NexusTrailGet(sig,"profile_tp2_pct",30));NexusTrailSet(sig,"runner_pct",40);
     }

public:
   CNexusTrailingEngine():m_tm(NULL),m_magic(258025),m_tf(PERIOD_M1),m_default_tf(PERIOD_M1){}
   void Configure(CNexusTradeManager *tm,const long magic,const ENUM_TIMEFRAMES tf){m_tm=tm;m_magic=magic;m_tf=tf;m_default_tf=tf;}

   void ManageAll(const bool manage_manual=false,const string manual_profile="NEXUS_TRAIL_07")
     {
      if(m_tm==NULL)return;
      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong ticket=PositionGetTicket(i); if(ticket==0||!PositionSelectByTicket(ticket))continue;
         long magic=(long)PositionGetInteger(POSITION_MAGIC); bool nexus=magic==m_magic; bool manual=!nexus&&manage_manual; if(!nexus&&!manual)continue;
         string sig=PositionGetString(POSITION_COMMENT); long id=(long)PositionGetInteger(POSITION_IDENTIFIER);
         if(manual){sig="MANUAL."+(string)id;InitManual(ticket,id,sig,manual_profile);} else {sig=NexusTrailSignalForTicket(ticket,sig);if(sig=="")continue;}
         int mode=(int)NexusTrailGet(sig,"mode",0); if(mode<1||mode>7)continue;
         m_tf=SignalTF(sig);
         string symbol=PositionGetString(POSITION_SYMBOL); ENUM_POSITION_TYPE pt=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE); double entry=PositionGetDouble(POSITION_PRICE_OPEN);

         MqlTick tick;
         if(!SymbolInfoTick(symbol,tick))continue;
         long tick_msc=(long)tick.time_msc;
         if(tick_msc<=0)tick_msc=(long)TimeCurrent()*1000;

         // Multi-chart safe ownership, now per broker tick instead of per
         // second. Only one EA instance may manage this signal for a tick.
         if(!NexusTrailClaimManageTick(sig,tick_msc))continue;

         double risk=MathAbs(entry-NexusTrailGet(sig,"initial_sl",PositionGetDouble(POSITION_SL))); if(risk<=0)continue;
         double px=pt==POSITION_TYPE_BUY?tick.bid:tick.ask; if(px<=0)continue;
         double pr=R(pt,px,entry,risk);
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
            Partials(ticket,sig,pt,px,entry,risk);
            if(PositionSelectByTicket(ticket) && NexusTrailGet(sig,"tp1_done",0)>0.5)
              {
               double runner_pr=R(pt,Price(symbol,pt),entry,risk);
               RunnerTrail(ticket,sig,pt,symbol,runner_pr);
              }
           }
         else if(mode==6)
            Step(ticket,sig,pt,entry,risk,pr,NexusTrailGet(sig,"break_even_r",.5),NexusTrailGet(sig,"trail_step_r",.35),NexusTrailGet(sig,"lock_step_r",.25));
         else
           {
            if(pr>=NexusTrailGet(sig,"break_even_r",1)) BE(ticket,sig,pt,entry);
            Partials(ticket,sig,pt,px,entry,risk);
            if(PositionSelectByTicket(ticket) && NexusTrailGet(sig,"tp1_done",0)>0.5)
              {
               // Structure is authoritative when available. ATR is used only
               // when no valid swing structure can be found.
               double runner_pr=R(pt,Price(symbol,pt),entry,risk);
               RunnerTrail(ticket,sig,pt,symbol,runner_pr);
              }
           }
        }
     }
  };
#endif

// UI65 build shim: compile NEXUS_AutoTrade_UI65.mq5 from this directory.
// The execution core remains the production source under ../NEXUS_AutoTrade.
//
// v0.6.6.1 wraps only the timer/trade-transaction entry points so exact MT5
// partial-deal truth can be queued/retried without modifying the hardened core.
// All other core event mappings supplied by the UI65 shell remain unchanged.
#undef OnTimer
#undef OnTradeTransaction
#define OnTimer            NEXUSCoreBase_OnTimer
#define OnTradeTransaction NEXUSCoreBase_OnTradeTransaction
#include "Core/NEXUS_AutoTrade_Core.mq5"
#undef OnTimer
#undef OnTradeTransaction

#include "Core/Include/PartialLifecycleTruth.mqh"

void NEXUSCore_OnTimer()
  {
   // Deliver pending partial stages before the core processes a possible final
   // CLOSE. This preserves Telegram lifecycle ordering after a transient outage.
   NexusPartialTruthProcessPending();
   NEXUSCoreBase_OnTimer();
  }

void NEXUSCore_OnTradeTransaction(const MqlTradeTransaction &trans,
                                  const MqlTradeRequest &request,
                                  const MqlTradeResult &result)
  {
   // Core remains authoritative for execution state and final-close queuing.
   NEXUSCoreBase_OnTradeTransaction(trans,request,result);
   // Post-core hook can now distinguish a partial exit because the position is
   // still present after MT5 has applied the exit deal.
   NexusPartialTruthOnTradeTransaction(trans,request,result);
  }

// Restore the names expected by the outer UI65 shell. It undefines these after
// this include and exposes its own thin UI-aware terminal event handlers.
#define OnTimer            NEXUSCore_OnTimer
#define OnTradeTransaction NEXUSCore_OnTradeTransaction

// The UI65 shell repaints visual controls after delegated core events/timers.
// MT5 OBJ_EDIT loses native keyboard focus if SELECTED is forced false during
// that repaint, and re-setting identical text can move the caret. Setup also
// rebuilds its chrome, so the focused License/Admin edit must not be deleted.
// These wrappers are defined *after* the production core include, therefore
// hardened trading/runtime code is never intercepted.
bool UI65IsFocusedEdit(const long chart_id,const string name)
  {
   if(StringFind(name,NXS_UI_PREFIX)!=0) return false;
   if(ObjectFind(chart_id,name)<0) return false;
   if((ENUM_OBJECT)ObjectGetInteger(chart_id,name,OBJPROP_TYPE)!=OBJ_EDIT) return false;
   return (bool)ObjectGetInteger(chart_id,name,OBJPROP_SELECTED);
  }

bool UI65IsFocusedSetupEdit(const long chart_id,const string name)
  {
   if(!g_setup_required) return false;
   if(name!=NXS_UI_PREFIX+"license" && name!=NXS_UI_PREFIX+"admin") return false;
   return UI65IsFocusedEdit(chart_id,name);
  }

bool UI65ObjectDeleteCompat(const long chart_id,const string name)
  {
   if(UI65IsFocusedSetupEdit(chart_id,name)) return true;
   return ObjectDelete(chart_id,name);
  }

bool UI65ObjectSetIntegerCompat(const long chart_id,const string name,
                                const ENUM_OBJECT_PROPERTY_INTEGER property_id,
                                const long value)
  {
   if(property_id==OBJPROP_SELECTED && value==0 && UI65IsFocusedEdit(chart_id,name))
      return true;
   return ObjectSetInteger(chart_id,name,property_id,value);
  }

bool UI65ObjectSetStringCompat(const long chart_id,const string name,
                               const ENUM_OBJECT_PROPERTY_STRING property_id,
                               const string value)
  {
   if(property_id==OBJPROP_TEXT && UI65IsFocusedEdit(chart_id,name))
     {
      string current=ObjectGetString(chart_id,name,property_id);
      if(current==value) return true;
     }
   return ObjectSetString(chart_id,name,property_id,value);
  }

#define ObjectDelete      UI65ObjectDeleteCompat
#define ObjectSetInteger  UI65ObjectSetIntegerCompat
#define ObjectSetString   UI65ObjectSetStringCompat

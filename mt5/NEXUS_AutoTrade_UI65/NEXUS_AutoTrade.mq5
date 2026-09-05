// UI65 build shim: compile NEXUS_AutoTrade_UI65.mq5 from this directory.
// The execution core remains the production source under ../NEXUS_AutoTrade.
#include "../NEXUS_AutoTrade/NEXUS_AutoTrade.mq5"

// The UI65 shell repaints its setup chrome after delegated chart events.
// MT5 OBJ_EDIT loses native keyboard focus if the active edit object is deleted
// or if SELECTED is forced false during that repaint.  Keep only the currently
// focused License/Admin edit alive; every other object operation is delegated
// to the native MQL5 API unchanged.  These macros are defined *after* the
// production core include, so hardened trading/runtime code is never wrapped.
bool UI65IsFocusedSetupEdit(const long chart_id,const string name)
  {
   if(!g_setup_required) return false;
   if(name!=NXS_UI_PREFIX+"license" && name!=NXS_UI_PREFIX+"admin") return false;
   if(ObjectFind(chart_id,name)<0) return false;
   return (bool)ObjectGetInteger(chart_id,name,OBJPROP_SELECTED);
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
   if(property_id==OBJPROP_SELECTED && value==0 && UI65IsFocusedSetupEdit(chart_id,name))
      return true;
   return ObjectSetInteger(chart_id,name,property_id,value);
  }

#define ObjectDelete      UI65ObjectDeleteCompat
#define ObjectSetInteger  UI65ObjectSetIntegerCompat

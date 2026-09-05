// UI65 build shim: compile NEXUS_AutoTrade_UI65.mq5 from this directory.
// The execution core remains the production source under ../NEXUS_AutoTrade.
#include "../NEXUS_AutoTrade/NEXUS_AutoTrade.mq5"

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

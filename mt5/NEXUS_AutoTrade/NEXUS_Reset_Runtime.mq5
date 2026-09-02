#property strict
#property script_show_inputs
#property description "One-time NEXUS runtime-memory reset. Does not delete user license/config file."

input bool InpResetAllNexusGlobals=true;

void OnStart()
  {
   if(!InpResetAllNexusGlobals)
     {
      Print("NEXUS reset cancelled: InpResetAllNexusGlobals=false");
      return;
     }

   int total=GlobalVariablesTotal();
   int deleted=0;
   for(int i=total-1;i>=0;i--)
     {
      string name=GlobalVariableName(i);
      if(StringFind(name,"NXS.")==0 || StringFind(name,"NXS_")==0)
        {
         if(GlobalVariableDel(name)) deleted++;
        }
     }

   PrintFormat("NEXUS runtime memory reset complete. Deleted %d Global Variables.",deleted);
  }

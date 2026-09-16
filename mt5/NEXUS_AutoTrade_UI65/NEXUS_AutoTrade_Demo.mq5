#property strict
#property description "NEXUS AutoTrade Demo/Test Lab - demo accounts only"

// Reuse the production Core byte-for-byte while replacing only its OnInit
// entrypoint. This keeps execution/trailing behavior identical to production
// and adds one hard safety rule: this wrapper refuses non-demo accounts.
#define OnInit NEXUS_Demo_Core_OnInit
#include "Core/NEXUS_AutoTrade_Core.mq5"
#undef OnInit

int OnInit()
  {
   long trade_mode=AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(trade_mode!=ACCOUNT_TRADE_MODE_DEMO)
     {
      Print("NEXUS DEMO TEST LAB BLOCKED | account=",AccountInfoInteger(ACCOUNT_LOGIN),
            " | reason=ACCOUNT_IS_NOT_DEMO");
      return INIT_FAILED;
     }

   Print("NEXUS DEMO TEST LAB | account=",AccountInfoInteger(ACCOUNT_LOGIN),
         " | safety=DEMO_ONLY | core=production");
   return NEXUS_Demo_Core_OnInit();
  }

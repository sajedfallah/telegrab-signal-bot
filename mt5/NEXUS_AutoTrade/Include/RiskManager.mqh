#ifndef NEXUS_RISK_MANAGER_MQH
#define NEXUS_RISK_MANAGER_MQH

#include "NexusTypes.mqh"

class CNexusRiskManager
  {
private:
   string m_last_error;

   double NormalizeVolume(const string symbol,double volume)
     {
      double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double maxv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      if(step<=0) step=minv;
      volume=MathMax(minv,MathMin(maxv,volume));
      volume=MathFloor(volume/step+1e-9)*step;
      int digits=0;
      double x=step;
      while(digits<8 && MathAbs(x-MathRound(x))>1e-9) { x*=10.0; digits++; }
      return NormalizeDouble(volume,digits);
     }

public:
   CNexusRiskManager():m_last_error("") {}

   string LastError() const { return m_last_error; }

   double FixedLot(const string symbol,const double requested)
     {
      return NormalizeVolume(symbol,requested);
     }

   double RiskLot(const string symbol,const ENUM_ORDER_TYPE order_type,const double open_price,const double stop_price,const double risk_percent)
     {
      m_last_error="";
      if(risk_percent<=0 || open_price<=0 || stop_price<=0 || open_price==stop_price)
        { m_last_error="invalid risk sizing inputs"; return 0; }
      double balance=AccountInfoDouble(ACCOUNT_BALANCE);
      double risk_money=balance*(risk_percent/100.0);
      double one_lot_profit=0;
      ResetLastError();
      if(!OrderCalcProfit(order_type,symbol,1.0,open_price,stop_price,one_lot_profit))
        { m_last_error="OrderCalcProfit failed error="+(string)GetLastError(); return 0; }
      double loss_one_lot=MathAbs(one_lot_profit);
      if(loss_one_lot<=0)
        { m_last_error="one-lot stop loss value is zero"; return 0; }
      double raw_volume=risk_money/loss_one_lot;
      double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      double maxv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      if(minv>0 && raw_volume<minv)
        {
         m_last_error=StringFormat("risk size %.8f is below broker minimum %.8f (balance=%.2f risk_money=%.2f loss_1lot=%.2f step=%.8f)",raw_volume,minv,balance,risk_money,loss_one_lot,step);
         return 0;
        }
      double normalized=NormalizeVolume(symbol,raw_volume);
      if(normalized<=0)
        { m_last_error=StringFormat("normalized risk size is zero (raw=%.8f min=%.8f step=%.8f max=%.8f)",raw_volume,minv,step,maxv); return 0; }
      return normalized;
     }
  };

#endif

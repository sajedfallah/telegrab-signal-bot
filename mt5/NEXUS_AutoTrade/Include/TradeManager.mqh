#ifndef NEXUS_TRADE_MANAGER_MQH
#define NEXUS_TRADE_MANAGER_MQH

#include <Trade/Trade.mqh>
#include "NexusTypes.mqh"
#include "RiskManager.mqh"

ENUM_TIMEFRAMES NexusTimeframeFromString(const string value)
  {
   string v=value; StringToUpper(v);
   if(v=="M1") return PERIOD_M1; if(v=="M3") return PERIOD_M3; if(v=="M5") return PERIOD_M5;
   if(v=="M15") return PERIOD_M15; if(v=="M30") return PERIOD_M30; if(v=="H1") return PERIOD_H1;
   if(v=="H4") return PERIOD_H4; if(v=="D1") return PERIOD_D1; if(v=="W1") return PERIOD_W1;
   return PERIOD_M1;
  }

class CNexusTradeManager
  {
private:
   CTrade m_trade;
   CNexusRiskManager m_risk;
   long m_magic;
   string m_last_error;
   bool   m_last_retryable;
   int    m_limit_expiration_hours;
   bool   m_strict_limit_checks;

   bool IsBuyDirection(const string d) { return d=="BUY" || d=="LONG"; }

   string Prefix(const string signal_id)
     {
      string s=signal_id;
      StringReplace(s," ","_");
      return "NXS."+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"."+s+".";
     }

   void SaveDouble(const string signal_id,const string field,const double value)
     {
      GlobalVariableSet(Prefix(signal_id)+field,value);
     }

   ulong SavedTicket(const string signal_id)
     {
      string key=Prefix(signal_id)+"ticket";
      if(!GlobalVariableCheck(key)) return 0;
      return (ulong)MathRound(GlobalVariableGet(key));
     }

   double NormalizePrice(const string symbol,const double value)
     {
      int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
      return NormalizeDouble(value,digits);
     }

   double BrokerMinDistance(const string symbol)
     {
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      long stops=SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
      long freeze=SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
      long level=MathMax(stops,freeze);
      return MathMax(0.0,(double)level*point);
     }

   bool ResolveLimitOrderTime(const string symbol,ENUM_ORDER_TYPE_TIME &time_type,datetime &expiration)
     {
      long modes=SymbolInfoInteger(symbol,SYMBOL_EXPIRATION_MODE);
      expiration=0;
      if(m_limit_expiration_hours>0)
        {
         if((modes & SYMBOL_EXPIRATION_SPECIFIED)!=0)
           { time_type=ORDER_TIME_SPECIFIED; expiration=TimeCurrent()+m_limit_expiration_hours*3600; return true; }
         if((modes & SYMBOL_EXPIRATION_DAY)!=0) { time_type=ORDER_TIME_DAY; return true; }
         if((modes & SYMBOL_EXPIRATION_GTC)!=0) { time_type=ORDER_TIME_GTC; return true; }
         return false;
        }
      if((modes & SYMBOL_EXPIRATION_GTC)!=0) { time_type=ORDER_TIME_GTC; return true; }
      if((modes & SYMBOL_EXPIRATION_DAY)!=0) { time_type=ORDER_TIME_DAY; return true; }
      if((modes & SYMBOL_EXPIRATION_SPECIFIED)!=0) { time_type=ORDER_TIME_SPECIFIED; expiration=TimeCurrent()+24*3600; return true; }
      return false;
     }

   bool ValidatePendingGeometry(const NexusSignal &s,const string symbol,const bool buy,const bool stop_order,string &reason)
     {
      double ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
      double bid=SymbolInfoDouble(symbol,SYMBOL_BID);
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      if(ask<=0 || bid<=0 || point<=0) { reason="broker has no valid Bid/Ask/Point"; return false; }
      double entry=NormalizePrice(symbol,s.entry);
      double sl=NormalizePrice(symbol,s.sl);
      double min_dist=BrokerMinDistance(symbol);
      if(buy)
        {
         if(stop_order ? (entry<=ask+min_dist) : (entry>=ask-min_dist)) { reason=StringFormat("BUY %s entry %.10f violates Ask %.10f (min distance %.10f)",stop_order?"STOP":"LIMIT",entry,ask,min_dist); return false; }
         if(sl<=0 || sl>=entry-min_dist) { reason=StringFormat("BUY LIMIT SL %.10f violates minimum distance %.10f from entry %.10f",sl,min_dist,entry); return false; }
        }
      else
        {
         if(stop_order ? (entry>=bid-min_dist) : (entry<=bid+min_dist)) { reason=StringFormat("SELL %s entry %.10f violates Bid %.10f (min distance %.10f)",stop_order?"STOP":"LIMIT",entry,bid,min_dist); return false; }
         if(sl<=entry+min_dist) { reason=StringFormat("SELL LIMIT SL %.10f violates minimum distance %.10f from entry %.10f",sl,min_dist,entry); return false; }
        }
      double tp=0;
      if(s.has_tp1) tp=NormalizePrice(symbol,s.tp1);
      if(tp>0)
        {
         if(buy && tp<=entry+min_dist) { reason=StringFormat("BUY pending TP %.10f violates minimum distance %.10f from entry %.10f",tp,min_dist,entry); return false; }
         if(!buy && tp>=entry-min_dist) { reason=StringFormat("SELL pending TP %.10f violates minimum distance %.10f from entry %.10f",tp,min_dist,entry); return false; }
        }
      return true;
     }

   // Backward-compatible name retained for existing static/integration tests.
   bool ValidateLimitGeometry(const NexusSignal &s,const string symbol,const bool buy,string &reason)
     {
      return ValidatePendingGeometry(s,symbol,buy,false,reason);
     }

public:
   CNexusTradeManager():m_magic(258025),m_last_error(""),m_last_retryable(false),m_limit_expiration_hours(0),m_strict_limit_checks(true) {}

   void Configure(const long magic,const int limit_expiration_hours=0,const bool strict_limit_checks=true)
     {
      m_magic=magic;
      m_limit_expiration_hours=MathMax(0,limit_expiration_hours);
      m_strict_limit_checks=strict_limit_checks;
      m_trade.SetExpertMagicNumber(m_magic);
      m_trade.SetTypeFillingBySymbol(_Symbol);
      m_trade.SetAsyncMode(false);
     }

   string LastError() const { return m_last_error; }
   bool LastFailureRetryable() const { return m_last_retryable; }

   bool HasSignalPosition(const string signal_id)
     {
      ulong saved=SavedTicket(signal_id);
      if(saved>0 && PositionSelectByTicket(saved) &&
         (long)PositionGetInteger(POSITION_MAGIC)==m_magic)
         return true;
      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong ticket=PositionGetTicket(i);
         if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
         if((long)PositionGetInteger(POSITION_MAGIC)!=m_magic) continue;
         if(PositionGetString(POSITION_COMMENT)==signal_id) return true;
        }
      return false;
     }

   bool HasSignalOrder(const string signal_id)
     {
      ulong saved=SavedTicket(signal_id);
      if(saved>0 && OrderSelect(saved) &&
         (long)OrderGetInteger(ORDER_MAGIC)==m_magic)
         return true;
      for(int i=OrdersTotal()-1;i>=0;i--)
        {
         ulong ticket=OrderGetTicket(i);
         if(ticket==0 || !OrderSelect(ticket)) continue;
         if((long)OrderGetInteger(ORDER_MAGIC)!=m_magic) continue;
         if(OrderGetString(ORDER_COMMENT)==signal_id) return true;
        }
      return false;
     }

   bool HasOtherNexusPositionOnNettingSymbol(const string symbol,const string signal_id)
     {
      long mode=AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      if(mode==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING) return false;
      if(!PositionSelect(symbol)) return false;
      // A netting account has one aggregate position per symbol. Do not
      // merge an EA signal into a manual/other-EA position.
      if((long)PositionGetInteger(POSITION_MAGIC)!=m_magic) return true;
      return PositionGetString(POSITION_COMMENT)!=signal_id;
     }

   ulong FindTicket(const string signal_id)
     {
      ulong saved=SavedTicket(signal_id);
      if(saved>0 && PositionSelectByTicket(saved) &&
         (long)PositionGetInteger(POSITION_MAGIC)==m_magic)
         return saved;
      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong ticket=PositionGetTicket(i);
         if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
         if((long)PositionGetInteger(POSITION_MAGIC)!=m_magic) continue;
         if(PositionGetString(POSITION_COMMENT)==signal_id) return ticket;
        }
      return 0;
     }

   bool ConfirmSignalPosition(const string signal_id,const string symbol,ulong &ticket)
     {
      for(int attempt=0;attempt<10;attempt++)
        {
         ticket=FindTicket(signal_id);
         if(ticket>0 && PositionSelectByTicket(ticket) &&
            (long)PositionGetInteger(POSITION_MAGIC)==m_magic &&
            (PositionGetString(POSITION_COMMENT)==signal_id || SavedTicket(signal_id)==ticket) &&
            PositionGetString(POSITION_SYMBOL)==symbol)
            return true;
         if(attempt<9) Sleep(100);
        }
      ticket=0;
      return false;
     }

   bool ConfirmSignalOrder(const ulong order_ticket,const string signal_id,const string symbol)
     {
      if(order_ticket==0) return false;
      for(int attempt=0;attempt<10;attempt++)
        {
         if(OrderSelect(order_ticket) &&
            (long)OrderGetInteger(ORDER_MAGIC)==m_magic &&
            (OrderGetString(ORDER_COMMENT)==signal_id || SavedTicket(signal_id)==order_ticket) &&
            OrderGetString(ORDER_SYMBOL)==symbol)
            return true;
         if(attempt<9) Sleep(100);
        }
      return false;
     }

   bool ValidateEntry(const NexusSignal &s,const string symbol,const double default_deviation_pct,string &reason)
     {
      // Pending LIMIT orders are placed at the requested Entry; market-deviation rejection applies only to MARKET signals.
      if(s.order_type!="MARKET") return true;
      bool buy=IsBuyDirection(s.direction);
      double market=buy?SymbolInfoDouble(symbol,SYMBOL_ASK):SymbolInfoDouble(symbol,SYMBOL_BID);
      if(market<=0 || s.entry<=0) { reason="invalid market/entry price"; return false; }
      double diff=MathAbs(market-s.entry);
      if(s.has_max_entry_deviation_abs && s.max_entry_deviation_abs>=0 && diff>s.max_entry_deviation_abs)
        {
         reason=StringFormat("entry deviation %.5f exceeds allowed %.5f",diff,s.max_entry_deviation_abs);
         return false;
        }
      double maxpct=s.has_max_entry_deviation_pct?s.max_entry_deviation_pct:default_deviation_pct;
      double pct=diff/s.entry*100.0;
      if(!s.has_max_entry_deviation_abs && maxpct>=0 && pct>maxpct)
        {
         reason=StringFormat("entry deviation %.5f%% exceeds %.5f%%",pct,maxpct);
         return false;
        }
      return true;
     }

   bool OpenSignal(const NexusSignal &s,const string symbol,const ENUM_NEXUS_RISK_MODE risk_mode,const double fixed_lot,const double user_risk_pct,ulong &ticket)
     {
      ticket=0; m_last_error=""; m_last_retryable=false;
      if(s.order_type!="MARKET" && s.order_type!="BUY_LIMIT" && s.order_type!="SELL_LIMIT" &&
         s.order_type!="BUY_STOP" && s.order_type!="SELL_STOP" &&
         s.order_type!="BUY_STOP_LIMIT" && s.order_type!="SELL_STOP_LIMIT" && s.order_type!="LIMIT")
        {
         m_last_error="unsupported order type: "+s.order_type;
         return false;
        }
      // Legacy LIMIT resolves from direction for backward compatibility.
      string normalized_type=s.order_type;
      if(normalized_type=="LIMIT") normalized_type=(IsBuyDirection(s.direction)?"BUY_LIMIT":"SELL_LIMIT");
      if(HasSignalPosition(s.signal_id)) { m_last_error="signal already has an open position"; return false; }
      if(HasSignalOrder(s.signal_id)) { m_last_error="signal already has a pending order"; return false; }
      if(HasOtherNexusPositionOnNettingSymbol(symbol,s.signal_id)) { m_last_error="netting account already has another NEXUS position on this symbol"; return false; }
      bool buy=IsBuyDirection(s.direction);
      ENUM_ORDER_TYPE order_type=buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
      double price=buy?SymbolInfoDouble(symbol,SYMBOL_ASK):SymbolInfoDouble(symbol,SYMBOL_BID);
      if(price<=0) { m_last_error="no market price"; m_last_retryable=true; return false; }
      if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
        { m_last_error="terminal trading is disabled (Algo Trading/Expert trading not allowed)"; m_last_retryable=false; return false; }
      long trade_mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
      if(trade_mode==SYMBOL_TRADE_MODE_DISABLED || trade_mode==SYMBOL_TRADE_MODE_CLOSEONLY)
        { m_last_error="broker symbol trading mode does not allow new positions: "+(string)trade_mode; m_last_retryable=false; return false; }
      if(buy && trade_mode==SYMBOL_TRADE_MODE_SHORTONLY)
        { m_last_error="broker symbol is SHORT_ONLY; BUY blocked"; m_last_retryable=false; return false; }
      if(!buy && trade_mode==SYMBOL_TRADE_MODE_LONGONLY)
        { m_last_error="broker symbol is LONG_ONLY; SELL blocked"; m_last_retryable=false; return false; }
      // NEXUS locked sizing: the admin-selected signal mode is authoritative.
      // User-side sizing settings are intentionally ignored for new NEXUS signals.
      double volume=0;
      if(s.volume_mode=="FIXED")
        {
         if(!s.has_lot_size || s.lot_size<=0) { m_last_error="fixed-lot signal has no valid lot size"; m_last_retryable=false; return false; }
         volume=m_risk.FixedLot(symbol,s.lot_size);
        }
      else
        {
         if(s.risk_percent<=0) { m_last_error="risk-managed signal has no valid risk percent"; m_last_retryable=false; return false; }
         double sizing_price=(normalized_type=="MARKET"?price:s.entry);
         volume=m_risk.RiskLot(symbol,order_type,sizing_price,s.sl,s.risk_percent);
        }
      if(volume<=0)
        {
         string sizing_reason=m_risk.LastError();
         m_last_error=(sizing_reason=="" ? "lot calculation failed" : "lot calculation failed: "+sizing_reason);
         m_last_retryable=false;
         Print("NEXUS SIZING FAILED | symbol=",symbol," mode=",s.volume_mode," risk%=",DoubleToString(s.risk_percent,4)," detail=",m_last_error);
         return false;
        }
      double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double maxv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      double stepv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      if(volume<minv || volume>maxv || (stepv>0 && MathAbs(volume/stepv-MathRound(volume/stepv))>1e-6))
        { m_last_error=StringFormat("invalid normalized volume %.8f (min=%.8f max=%.8f step=%.8f)",volume,minv,maxv,stepv); m_last_retryable=false; return false; }
      double margin=0; ResetLastError();
      if(!OrderCalcMargin(order_type,symbol,volume,price,margin))
        { m_last_error="OrderCalcMargin failed error="+(string)GetLastError(); m_last_retryable=true; return false; }
      double free_margin=AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      if(margin>free_margin)
        { m_last_error=StringFormat("insufficient free margin: required=%.2f free=%.2f volume=%.8f",margin,free_margin,volume); m_last_retryable=false; return false; }

      int mode=NexusTrailingModeNumber(s.trailing_code);
      double final_tp=0;
      if(mode!=5 && mode!=7)
        {
         if(s.has_tp10) final_tp=s.tp10;
         else if(s.has_tp9) final_tp=s.tp9;
         else if(s.has_tp8) final_tp=s.tp8;
         else if(s.has_tp7) final_tp=s.tp7;
         else if(s.has_tp6) final_tp=s.tp6;
         else if(s.has_tp5) final_tp=s.tp5;
         else if(s.has_tp4) final_tp=s.tp4;
         else if(s.has_tp3) final_tp=s.tp3;
         else if(s.has_tp2) final_tp=s.tp2;
         else if(s.has_tp1) final_tp=s.tp1;
        }
      m_trade.SetTypeFillingBySymbol(symbol);
      bool ok=false;
      if(normalized_type!="MARKET")
        {
         if(m_strict_limit_checks)
           {
            string geometry_reason="";
            bool stop_order=(normalized_type=="BUY_STOP" || normalized_type=="SELL_STOP" || normalized_type=="BUY_STOP_LIMIT" || normalized_type=="SELL_STOP_LIMIT");
            if((normalized_type=="BUY_STOP_LIMIT" || normalized_type=="SELL_STOP_LIMIT") && s.stop_limit_price<=0)
              { m_last_error="PENDING validation failed: stop_limit_price is required"; m_last_retryable=false; return false; }
            if(!ValidatePendingGeometry(s,symbol,buy,stop_order,geometry_reason))
              { m_last_error="PENDING validation failed: "+geometry_reason; m_last_retryable=false; return false; }
           }
         ENUM_ORDER_TYPE_TIME time_type=ORDER_TIME_GTC;
         datetime expiration=0;
         if(!ResolveLimitOrderTime(symbol,time_type,expiration))
           { m_last_error="broker does not support a valid pending-order expiration mode"; m_last_retryable=false; return false; }
         double entry_price=NormalizePrice(symbol,s.entry);
         double sl_price=NormalizePrice(symbol,s.sl);
         double tp_price=(final_tp>0?NormalizePrice(symbol,final_tp):0);
         Print("NEXUS PENDING submit | symbol=",symbol," type=",normalized_type,
               " entry=",DoubleToString(entry_price,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS)),
               " sl=",DoubleToString(sl_price,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS)),
               " tp=",DoubleToString(tp_price,(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS)));
         // Submit all pending types through the stable MQL5 request API.
         // This preserves the exact order type and avoids optional CTrade
         // helpers that may be missing in older terminal standard libraries.
         MqlTradeRequest req;
         MqlTradeResult  res;
         ZeroMemory(req);
         ZeroMemory(res);
         req.action=TRADE_ACTION_PENDING;
         req.magic=m_magic;
         req.symbol=symbol;
         req.volume=volume;
         req.price=entry_price;
         req.sl=sl_price;
         req.tp=tp_price;
         req.type_time=time_type;
         req.expiration=expiration;
         req.type_filling=ORDER_FILLING_RETURN;
         req.comment=s.signal_id;

         if(normalized_type=="BUY_LIMIT") req.type=ORDER_TYPE_BUY_LIMIT;
         else if(normalized_type=="SELL_LIMIT") req.type=ORDER_TYPE_SELL_LIMIT;
         else if(normalized_type=="BUY_STOP") req.type=ORDER_TYPE_BUY_STOP;
         else if(normalized_type=="SELL_STOP") req.type=ORDER_TYPE_SELL_STOP;
         else if(normalized_type=="BUY_STOP_LIMIT")
           {
            req.type=ORDER_TYPE_BUY_STOP_LIMIT;
            req.stoplimit=NormalizePrice(symbol,s.stop_limit_price);
           }
         else if(normalized_type=="SELL_STOP_LIMIT")
           {
            req.type=ORDER_TYPE_SELL_STOP_LIMIT;
            req.stoplimit=NormalizePrice(symbol,s.stop_limit_price);
           }
         else { m_last_error="unsupported pending order type: "+normalized_type; return false; }

         ResetLastError();
         ok=OrderSend(req,res);
          if(!ok || (res.retcode!=TRADE_RETCODE_DONE && res.retcode!=TRADE_RETCODE_PLACED))
           {
            uint rc=res.retcode;
            m_last_error="pending order failed: "+IntegerToString((int)rc);
            if(res.comment!="") m_last_error+=" "+res.comment;
            m_last_retryable=(rc==TRADE_RETCODE_REQUOTE ||
                              rc==TRADE_RETCODE_TIMEOUT ||
                              rc==TRADE_RETCODE_PRICE_CHANGED ||
                              rc==TRADE_RETCODE_PRICE_OFF ||
                              rc==TRADE_RETCODE_TOO_MANY_REQUESTS ||
                              rc==TRADE_RETCODE_CONNECTION ||
                              rc==TRADE_RETCODE_MARKET_CLOSED ||
                              rc==TRADE_RETCODE_LOCKED);
            return false;
           }

          ticket=(ulong)res.order;
          if(!ConfirmSignalOrder(ticket,s.signal_id,symbol))
            {
             m_last_error=StringFormat("pending order not confirmed by broker: retcode=%d order=%I64u deal=%I64u error=%d",
                                       (int)res.retcode,res.order,res.deal,GetLastError());
             m_last_retryable=true;
             ticket=0;
             return false;
            }

        }
      else
        {
         double bid=SymbolInfoDouble(symbol,SYMBOL_BID);
         double ask=SymbolInfoDouble(symbol,SYMBOL_ASK);
         double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
         long stops=SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
         long freeze=SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);
         long trade_mode=SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
         long filling=SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE);
         Print("NEXUS MARKET PREFLIGHT | symbol=",symbol," bid=",DoubleToString(bid,8),
               " ask=",DoubleToString(ask,8)," volume=",DoubleToString(volume,8),
               " sl=",DoubleToString(s.sl,8)," tp=",DoubleToString(final_tp,8),
               " stops=",(string)stops," freeze=",(string)freeze," trade_mode=",(string)trade_mode,
               " filling_mode=",(string)filling," terminal_trade=",(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)?"YES":"NO"));
         long stops_level=SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
         double min_stop=(double)MathMax(0,stops_level)*point;
         double sl_price=NormalizePrice(symbol,s.sl);
         double tp_price=(final_tp>0?NormalizePrice(symbol,final_tp):0);
         if(buy)
           {
            if(sl_price<=0 || sl_price>=bid-min_stop) { m_last_error=StringFormat("BUY SL violates broker stop distance: sl=%.8f bid=%.8f min=%.8f",sl_price,bid,min_stop); return false; }
            if(tp_price>0 && tp_price<=ask+min_stop) { m_last_error=StringFormat("BUY TP violates broker stop distance: tp=%.8f ask=%.8f min=%.8f",tp_price,ask,min_stop); return false; }
           }
         else
           {
            if(sl_price<=ask+min_stop) { m_last_error=StringFormat("SELL SL violates broker stop distance: sl=%.8f ask=%.8f min=%.8f",sl_price,ask,min_stop); return false; }
            if(tp_price>0 && tp_price>=bid-min_stop) { m_last_error=StringFormat("SELL TP violates broker stop distance: tp=%.8f bid=%.8f min=%.8f",tp_price,bid,min_stop); return false; }
           }
          ResetLastError();
          ok=buy?m_trade.Buy(volume,symbol,0,sl_price,tp_price,s.signal_id):m_trade.Sell(volume,symbol,0,sl_price,tp_price,s.signal_id);
          uint market_rc=m_trade.ResultRetcode();
          if(ok && market_rc!=TRADE_RETCODE_DONE && market_rc!=TRADE_RETCODE_DONE_PARTIAL)
            {
             ok=false;
             m_last_error="trade request was not executed: "+m_trade.ResultRetcodeDescription()
                          +" [retcode="+IntegerToString((int)market_rc)
                          +" order="+(string)m_trade.ResultOrder()
                          +" deal="+(string)m_trade.ResultDeal()
                          +" error="+(string)GetLastError()+"]";
            }
         }
      if(!ok)
        {
         uint rc=m_trade.ResultRetcode();
         m_last_error=(s.order_type=="LIMIT"?"limit order failed: ":"trade open failed: ")+m_trade.ResultRetcodeDescription()
                      +" [retcode="+IntegerToString((int)rc)+"]";
         // Retry only failures that may clear without changing the signal itself.
         m_last_retryable=(rc==TRADE_RETCODE_REQUOTE ||
                           rc==TRADE_RETCODE_TIMEOUT ||
                           rc==TRADE_RETCODE_PRICE_CHANGED ||
                           rc==TRADE_RETCODE_PRICE_OFF ||
                           rc==TRADE_RETCODE_TOO_MANY_REQUESTS ||
                           rc==TRADE_RETCODE_CONNECTION ||
                           rc==TRADE_RETCODE_MARKET_CLOSED ||
                           rc==TRADE_RETCODE_LOCKED);
         return false;
        }
       if(normalized_type=="MARKET" && !ConfirmSignalPosition(s.signal_id,symbol,ticket))
         {
          uint rc=m_trade.ResultRetcode();
          m_last_error=StringFormat("market execution not confirmed by broker position: retcode=%d order=%I64u deal=%I64u error=%d",
                                    (int)rc,m_trade.ResultOrder(),m_trade.ResultDeal(),GetLastError());
          m_last_retryable=true;
          ticket=0;
          return false;
         }

      // Persistent state used for restart-safe management.
      SaveDouble(s.signal_id,"db_id",(double)s.db_id);
      // Some brokers clear POSITION_COMMENT after a partial close. Persist the
      // broker ticket so live-state/restart reconciliation can still recover
      // the canonical signal identity without trusting the mutable comment.
      SaveDouble(s.signal_id,"ticket",(double)ticket);
      SaveDouble(s.signal_id,"is_limit",normalized_type!="MARKET"?1:0);
      SaveDouble(s.signal_id,"activation_notified",normalized_type!="MARKET"?0:1);
      SaveDouble(s.signal_id,"mode",mode);
      SaveDouble(s.signal_id,"initial_sl",s.sl);
      SaveDouble(s.signal_id,"timeframe_code",(double)NexusTimeframeFromString(s.timeframe));
      SaveDouble(s.signal_id,"signal_entry",s.entry);
      SaveDouble(s.signal_id,"tp1",s.tp1); SaveDouble(s.signal_id,"has_tp1",s.has_tp1?1:0);
      SaveDouble(s.signal_id,"tp2",s.tp2); SaveDouble(s.signal_id,"has_tp2",s.has_tp2?1:0);
      SaveDouble(s.signal_id,"tp3",s.tp3); SaveDouble(s.signal_id,"has_tp3",s.has_tp3?1:0);
      SaveDouble(s.signal_id,"tp4",s.tp4); SaveDouble(s.signal_id,"has_tp4",s.has_tp4?1:0);
      SaveDouble(s.signal_id,"tp5",s.tp5); SaveDouble(s.signal_id,"has_tp5",s.has_tp5?1:0);
      SaveDouble(s.signal_id,"tp6",s.tp6); SaveDouble(s.signal_id,"has_tp6",s.has_tp6?1:0);
      SaveDouble(s.signal_id,"tp7",s.tp7); SaveDouble(s.signal_id,"has_tp7",s.has_tp7?1:0);
      SaveDouble(s.signal_id,"tp8",s.tp8); SaveDouble(s.signal_id,"has_tp8",s.has_tp8?1:0);
      SaveDouble(s.signal_id,"tp9",s.tp9); SaveDouble(s.signal_id,"has_tp9",s.has_tp9?1:0);
      SaveDouble(s.signal_id,"tp10",s.tp10); SaveDouble(s.signal_id,"has_tp10",s.has_tp10?1:0);
      SaveDouble(s.signal_id,"be_done",0); for(int tp_i=1;tp_i<=10;tp_i++) SaveDouble(s.signal_id,"tp"+IntegerToString(tp_i)+"_done",0);
      SaveDouble(s.signal_id,"initial_volume",volume);
      SaveDouble(s.signal_id,"break_even_r",s.break_even_r);
      SaveDouble(s.signal_id,"trail_step_r",s.trail_step_r);
      SaveDouble(s.signal_id,"lock_step_r",s.lock_step_r);
      SaveDouble(s.signal_id,"atr_period",s.atr_period);
      SaveDouble(s.signal_id,"atr_multiplier",s.atr_multiplier);
      SaveDouble(s.signal_id,"activation_r",s.activation_r);
      SaveDouble(s.signal_id,"tp1_close_pct",s.tp1_close_pct);
      SaveDouble(s.signal_id,"tp2_close_pct",s.tp2_close_pct);
      SaveDouble(s.signal_id,"runner_pct",s.runner_pct);
      SaveDouble(s.signal_id,"swing_left",s.swing_left);
      SaveDouble(s.signal_id,"swing_right",s.swing_right);
      return true;
     }

   bool CloseAllNexus()
     {
      bool ok=true;
      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong ticket=PositionGetTicket(i);
         if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
         if((long)PositionGetInteger(POSITION_MAGIC)!=m_magic) continue;
         if(!m_trade.PositionClose(ticket)) ok=false;
        }
      for(int i=OrdersTotal()-1;i>=0;i--)
        {
         ulong ticket=OrderGetTicket(i);
         if(ticket==0 || !OrderSelect(ticket)) continue;
         if((long)OrderGetInteger(ORDER_MAGIC)!=m_magic) continue;
         if(!m_trade.OrderDelete(ticket)) ok=false;
        }
      return ok;
     }

   bool CloseSignal(const string signal_id)
     {
      m_last_error="";
      bool found=false;
      ulong saved=SavedTicket(signal_id);

      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong ticket=PositionGetTicket(i);
         if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
         if((long)PositionGetInteger(POSITION_MAGIC)!=m_magic) continue;
         // Some brokers clear POSITION_COMMENT after a partial close.  The
         // immutable broker ticket persisted at execution remains authoritative.
         if(PositionGetString(POSITION_COMMENT)!=signal_id && ticket!=saved) continue;
         found=true;
         string symbol=PositionGetString(POSITION_SYMBOL);
         m_trade.SetTypeFillingBySymbol(symbol);
         ResetLastError();
         bool sent=m_trade.PositionClose(ticket);
         uint rc=m_trade.ResultRetcode();
         if(!sent || (rc!=TRADE_RETCODE_DONE && rc!=TRADE_RETCODE_DONE_PARTIAL))
           {
            m_last_error="signal close failed: "+m_trade.ResultRetcodeDescription()+
                         " [signal="+signal_id+" ticket="+(string)ticket+
                         " retcode="+IntegerToString((int)rc)+" error="+(string)GetLastError()+"]";
            return false;
           }
         bool still_open=false;
         for(int attempt=0;attempt<10;attempt++)
           {
            still_open=PositionSelectByTicket(ticket);
            if(!still_open) break;
            if(attempt<9) Sleep(100);
           }
         if(still_open)
           {
            m_last_error="signal close not confirmed by broker [signal="+signal_id+" ticket="+(string)ticket+"]";
            return false;
           }
        }

      for(int i=OrdersTotal()-1;i>=0;i--)
        {
         ulong ticket=OrderGetTicket(i);
         if(ticket==0 || !OrderSelect(ticket)) continue;
         if((long)OrderGetInteger(ORDER_MAGIC)!=m_magic) continue;
         if(OrderGetString(ORDER_COMMENT)!=signal_id && ticket!=saved) continue;
         found=true;
         ResetLastError();
         bool sent=m_trade.OrderDelete(ticket);
         uint rc=m_trade.ResultRetcode();
         if(!sent || rc!=TRADE_RETCODE_DONE)
           {
            m_last_error="signal order cancel failed: "+m_trade.ResultRetcodeDescription()+
                         " [signal="+signal_id+" ticket="+(string)ticket+
                         " retcode="+IntegerToString((int)rc)+" error="+(string)GetLastError()+"]";
            return false;
           }
         bool still_pending=false;
         for(int attempt=0;attempt<10;attempt++)
           {
            still_pending=OrderSelect(ticket);
            if(!still_pending) break;
            if(attempt<9) Sleep(100);
           }
         if(still_pending)
           {
            m_last_error="signal order cancellation not confirmed by broker [signal="+signal_id+" ticket="+(string)ticket+"]";
            return false;
           }
        }

      if(!found)
        {
         m_last_error="no matching broker position or pending order for signal "+signal_id;
         return false;
        }
      return true;
     }

   bool ModifySL(const ulong ticket,const double new_sl)
     {
      if(!PositionSelectByTicket(ticket)) { m_last_error="position not found"; return false; }
      string symbol=PositionGetString(POSITION_SYMBOL);
      double tp=PositionGetDouble(POSITION_TP);
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      m_trade.SetTypeFillingBySymbol(symbol);
      ResetLastError();
      bool sent=m_trade.PositionModify(ticket,new_sl,tp);
      uint rc=m_trade.ResultRetcode();
      if(!sent || (rc!=TRADE_RETCODE_DONE && rc!=TRADE_RETCODE_DONE_PARTIAL && rc!=TRADE_RETCODE_NO_CHANGES))
        {
         m_last_error="SL modify failed: "+m_trade.ResultRetcodeDescription()+" [retcode="+IntegerToString((int)rc)+"]";
         return false;
        }
      double tolerance=MathMax(point*0.5,SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE));
      double actual=0;
      bool selected=false;
      for(int attempt=0;attempt<10;attempt++)
        {
         selected=PositionSelectByTicket(ticket);
         if(selected)
           {
            actual=PositionGetDouble(POSITION_SL);
            if(actual>0 && MathAbs(actual-new_sl)<=tolerance) break;
           }
         if(attempt<9) Sleep(100);
        }
      if(!selected) { m_last_error="SL modify sent but position disappeared"; return false; }
      if(actual<=0 || MathAbs(actual-new_sl)>tolerance)
        {
         m_last_error=StringFormat("SL modify not confirmed: requested=%.10f actual=%.10f retcode=%d",new_sl,actual,(int)rc);
         return false;
        }
      return true;
     }

   bool ModifyTP(const ulong ticket,const double new_tp)
     {
      if(!PositionSelectByTicket(ticket)) { m_last_error="position not found"; return false; }
      string symbol=PositionGetString(POSITION_SYMBOL);
      double sl=PositionGetDouble(POSITION_SL);
      double point=SymbolInfoDouble(symbol,SYMBOL_POINT);
      m_trade.SetTypeFillingBySymbol(symbol);
      ResetLastError();
      bool sent=m_trade.PositionModify(ticket,sl,new_tp);
      uint rc=m_trade.ResultRetcode();
      if(!sent || (rc!=TRADE_RETCODE_DONE && rc!=TRADE_RETCODE_DONE_PARTIAL && rc!=TRADE_RETCODE_NO_CHANGES))
        {
         m_last_error="TP modify failed: "+m_trade.ResultRetcodeDescription()+" [retcode="+IntegerToString((int)rc)+"]";
         return false;
        }
      double tolerance=MathMax(point*0.5,SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE));
      double actual=0;
      bool selected=false;
      for(int attempt=0;attempt<10;attempt++)
        {
         selected=PositionSelectByTicket(ticket);
         if(selected)
           {
            actual=PositionGetDouble(POSITION_TP);
            if((new_tp<=0 && actual==0) || (new_tp>0 && MathAbs(actual-new_tp)<=tolerance)) break;
           }
         if(attempt<9) Sleep(100);
        }
      if(!selected) { m_last_error="TP modify sent but position disappeared"; return false; }
      if(new_tp<=0)
        {
         if(actual!=0) { m_last_error=StringFormat("TP clear not confirmed: actual=%.10f retcode=%d",actual,(int)rc); return false; }
        }
      else if(MathAbs(actual-new_tp)>tolerance)
        {
         m_last_error=StringFormat("TP modify not confirmed: requested=%.10f actual=%.10f retcode=%d",new_tp,actual,(int)rc);
         return false;
        }
      return true;
     }

   bool PartialCloseVolume(const ulong ticket,double close_volume)
     {
      if(!PositionSelectByTicket(ticket)) { m_last_error="position not found"; return false; }
      string symbol=PositionGetString(POSITION_SYMBOL);
      double before=PositionGetDouble(POSITION_VOLUME);
      double minv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double maxv=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      if(before<=0 || minv<=0) { m_last_error="invalid broker position volume metadata"; return false; }
      if(step<=0) step=minv;

      // Broker-volume-grid aware partial close.
      // Example: 0.02 position, 30% requested = 0.006 while broker step/min
      // is 0.01. The old floor-to-step policy produced 0.00 forever.
      // Select the nearest executable broker volume while preserving at least
      // one valid minimum-volume runner whenever this is a partial target.
      double requested_close=close_volume;
      double eps=MathMax(step*0.1,1e-8);
      bool full_close_requested=(requested_close>=before-eps);

      if(full_close_requested)
        {
         close_volume=before;
        }
      else
        {
         double max_partial=before-minv;

         // There is no legal way to split a one-minimum-lot position.
         if(max_partial+eps<minv)
           {
            m_last_error=StringFormat(
               "partial close unavailable on broker volume grid: before=%.8f requested=%.8f min=%.8f step=%.8f",
               before,requested_close,minv,step
            );
            return false;
           }

         double units=MathRound(requested_close/step);
         close_volume=NormalizeDouble(units*step,8);

         if(close_volume<minv)
            close_volume=minv;

         if(close_volume>max_partial)
            close_volume=MathFloor(max_partial/step+1e-9)*step;

         close_volume=NormalizeDouble(close_volume,8);

         double adaptive_remain=before-close_volume;

         if(close_volume<minv || adaptive_remain+eps<minv)
           {
            m_last_error=StringFormat(
               "partial close has no executable broker-grid volume: before=%.8f requested=%.8f adapted=%.8f remain=%.8f min=%.8f step=%.8f",
               before,requested_close,close_volume,adaptive_remain,minv,step
            );
            return false;
           }

         if(MathAbs(close_volume-requested_close)>eps)
           {
            Print(
               "NEXUS PARTIAL ADAPTIVE VOLUME | ticket=",(string)ticket,
               " symbol=",symbol,
               " before=",DoubleToString(before,8),
               " requested=",DoubleToString(requested_close,8),
               " adapted=",DoubleToString(close_volume,8),
               " min=",DoubleToString(minv,8),
               " step=",DoubleToString(step,8)
            );
           }
        }

      double remain=before-close_volume;

      // Final-target/full-close path. Never mark success until MT5 confirms
      // that the position ticket is actually gone.
      if(close_volume>=before-eps)
        {
         m_trade.SetTypeFillingBySymbol(symbol);
         ResetLastError();
         bool sent=m_trade.PositionClose(ticket);
         uint rc=m_trade.ResultRetcode();
         if(!sent || (rc!=TRADE_RETCODE_DONE && rc!=TRADE_RETCODE_DONE_PARTIAL))
           {
            m_last_error="full close failed: "+m_trade.ResultRetcodeDescription()+" [retcode="+IntegerToString((int)rc)+"]";
            return false;
           }
         double after=before;
         for(int attempt=0;attempt<10;attempt++)
           {
            if(!PositionSelectByTicket(ticket)) return true;
            after=PositionGetDouble(POSITION_VOLUME);
            if(after<=eps) return true;
            if(attempt<9) Sleep(100);
           }
         m_last_error=StringFormat("full close not confirmed: before=%.8f after=%.8f retcode=%d",before,after,(int)rc);
         return false;
        }

      long mode=AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      m_trade.SetTypeFillingBySymbol(symbol);
      ResetLastError();
      bool sent=false;
      if(mode==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
         sent=m_trade.PositionClosePartial(ticket,close_volume);
      else
        {
         // Netting: reduce the position by sending an opposite market deal.
         ENUM_POSITION_TYPE pt=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         sent=(pt==POSITION_TYPE_BUY)?m_trade.Sell(close_volume,symbol):m_trade.Buy(close_volume,symbol);
        }
      uint rc=m_trade.ResultRetcode();
      if(!sent || (rc!=TRADE_RETCODE_DONE && rc!=TRADE_RETCODE_DONE_PARTIAL))
        {
         m_last_error=StringFormat("partial close failed: %s [retcode=%d requested=%.8f before=%.8f]",m_trade.ResultRetcodeDescription(),(int)rc,close_volume,before);
         return false;
        }

      // Execution truth: re-read the live position and require the volume to
      // have actually decreased by approximately the requested broker step.
      double expected=before-close_volume;
      double tolerance=MathMax(step*0.5,1e-8);
      double after=before;
      bool selected=false;
      bool confirmed=false;
      for(int attempt=0;attempt<10;attempt++)
        {
         selected=PositionSelectByTicket(ticket);
         if(!selected) break;
         after=PositionGetDouble(POSITION_VOLUME);
         if(after>0 && MathAbs(after-expected)<=tolerance)
           { confirmed=true; break; }
         if(attempt<9) Sleep(100);
        }
      if(!selected)
        {
         m_last_error=StringFormat("partial close unexpectedly removed position: before=%.8f requested=%.8f retcode=%d",before,close_volume,(int)rc);
         return false;
        }
      if(!confirmed)
        {
         m_last_error=StringFormat("partial close not confirmed: before=%.8f requested=%.8f expected_after=%.8f actual_after=%.8f retcode=%d",before,close_volume,expected,after,(int)rc);
         return false;
        }
      Print("NEXUS PARTIAL CONFIRMED | ticket=",(string)ticket," symbol=",symbol,
            " before=",DoubleToString(before,8)," closed=",DoubleToString(close_volume,8),
            " after=",DoubleToString(after,8)," retcode=",(string)rc);
      return true;
     }

   bool PartialClosePercent(const string signal_id,const double pct)
     {
      ulong ticket=FindTicket(signal_id);
      if(ticket==0) { m_last_error="position not found"; return false; }
      if(!PositionSelectByTicket(ticket)) return false;
      double current=PositionGetDouble(POSITION_VOLUME);
      return PartialCloseVolume(ticket,current*MathMax(0,MathMin(100,pct))/100.0);
     }
  };

#endif

#ifndef NEXUS_PARTIAL_LIFECYCLE_TRUTH_MQH
#define NEXUS_PARTIAL_LIFECYCLE_TRUTH_MQH

// v0.6.6.1 broker-deal truth bridge.
//
// A live-state volume reduction proves that a partial close happened, but its
// POSITION_PROFIT value is floating PnL for the remaining position.  Telegram
// stage-profit updates must instead come from the exact MT5 exit deal.  This
// bridge runs outside the hardened execution core: OnTradeTransaction queues
// exit deals, and OnTimer sends/retries the explicit UPDATE event.

struct NEXUSPartialTruthPending
  {
   long position_id;
   ulong deal_ticket;
   int attempts;
   datetime next_try;
  };

NEXUSPartialTruthPending g_partial_truth_pending[];
bool g_partial_truth_recovery_done=false;

int NexusPartialTruthFind(const ulong deal_ticket)
  {
   for(int i=0;i<ArraySize(g_partial_truth_pending);i++)
      if(g_partial_truth_pending[i].deal_ticket==deal_ticket) return i;
   return -1;
  }

void NexusPartialTruthRemove(const int idx)
  {
   if(idx<0 || idx>=ArraySize(g_partial_truth_pending)) return;
   int last=ArraySize(g_partial_truth_pending)-1;
   if(idx!=last) g_partial_truth_pending[idx]=g_partial_truth_pending[last];
   ArrayResize(g_partial_truth_pending,last);
  }

string NexusPartialTruthSignalId(const long position_id)
  {
   string signal_id=PositionSignalId(position_id);
   StringTrimLeft(signal_id);
   StringTrimRight(signal_id);
   if(StringFind(signal_id,"NX-")==0 || StringFind(signal_id,"MT5MANUAL-")==0)
      return signal_id;
   return "";
  }

bool NexusPartialTruthDealIsExit(const ulong deal_ticket,long &position_id)
  {
   position_id=0;
   if(deal_ticket==0 || !HistoryDealSelect(deal_ticket)) return false;
   long entry=HistoryDealGetInteger(deal_ticket,DEAL_ENTRY);
   // INOUT is a reversal semantic, not a partial reduction. Do not present it
   // as a partial-close stage.
   if(entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY) return false;
   position_id=(long)HistoryDealGetInteger(deal_ticket,DEAL_POSITION_ID);
   return position_id>0;
  }

bool NexusPartialTruthPositionStillExists(const long position_id,ulong &position_ticket)
  {
   position_ticket=PositionTicketByIdentifier(position_id);
   return position_ticket>0 && PositionSelectByTicket(position_ticket);
  }

void NexusPartialTruthQueue(const long position_id,const ulong deal_ticket)
  {
   if(position_id<=0 || deal_ticket==0) return;
   if(NexusPartialTruthFind(deal_ticket)>=0) return;
   int idx=ArraySize(g_partial_truth_pending);
   ArrayResize(g_partial_truth_pending,idx+1);
   g_partial_truth_pending[idx].position_id=position_id;
   g_partial_truth_pending[idx].deal_ticket=deal_ticket;
   g_partial_truth_pending[idx].attempts=0;
   g_partial_truth_pending[idx].next_try=TimeCurrent();
  }

void NexusPartialTruthOnTradeTransaction(const MqlTradeTransaction &trans,
                                         const MqlTradeRequest &request,
                                         const MqlTradeResult &result)
  {
   if(trans.type!=TRADE_TRANSACTION_DEAL_ADD || trans.deal==0) return;

   long position_id=0;
   if(!NexusPartialTruthDealIsExit(trans.deal,position_id)) return;

   // The core has already processed the transaction before this hook runs.
   // If the position still exists, this exit deal is a partial reduction. A
   // genuinely final exit is owned by the existing pending-CLOSE pipeline.
   ulong position_ticket=0;
   if(!NexusPartialTruthPositionStillExists(position_id,position_ticket)) return;
   if(NexusPartialTruthSignalId(position_id)=="") return;

   NexusPartialTruthQueue(position_id,trans.deal);
   Print("NEXUS PARTIAL TRUTH QUEUED | position=",(string)position_id,
         " deal=",(string)trans.deal," ticket=",(string)position_ticket);
  }

bool NexusPartialTruthSend(const long position_id,const ulong deal_ticket)
  {
   if(deal_ticket==0 || !HistoryDealSelect(deal_ticket)) return false;

   long deal_position=(long)HistoryDealGetInteger(deal_ticket,DEAL_POSITION_ID);
   if(deal_position!=position_id) return true; // corrupt/stale queue item: consume safely

   long entry=HistoryDealGetInteger(deal_ticket,DEAL_ENTRY);
   if(entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY) return true;

   string signal_id=NexusPartialTruthSignalId(position_id);
   if(signal_id=="") return true;

   string symbol=HistoryDealGetString(deal_ticket,DEAL_SYMBOL);
   string direction=OriginalDirectionForPosition(position_id);
   if(symbol=="" || direction=="") return false;

   double closed_volume=HistoryDealGetDouble(deal_ticket,DEAL_VOLUME);
   double exit_price=HistoryDealGetDouble(deal_ticket,DEAL_PRICE);
   if(closed_volume<=0 || exit_price<=0) return false;

   // Broker truth for this exact exit deal.  DEAL_PROFIT is gross trading PnL;
   // net stage PnL also includes swap, commission and broker fee.
   double gross_profit=HistoryDealGetDouble(deal_ticket,DEAL_PROFIT);
   double swap=HistoryDealGetDouble(deal_ticket,DEAL_SWAP);
   double commission=HistoryDealGetDouble(deal_ticket,DEAL_COMMISSION);
   commission+=HistoryDealGetDouble(deal_ticket,DEAL_FEE);
   double stage_profit=gross_profit+swap+commission;

   ulong position_ticket=0;
   double sl=HistoryDealGetDouble(deal_ticket,DEAL_SL);
   double tp=HistoryDealGetDouble(deal_ticket,DEAL_TP);
   if(NexusPartialTruthPositionStillExists(position_id,position_ticket))
     {
      sl=PositionGetDouble(POSITION_SL);
      tp=PositionGetDouble(POSITION_TP);
     }
   else
     {
      // The deal was already proven partial when it was queued. If the final
      // exit happened before a retry succeeds, preserve ordering by delivering
      // this stage before the core's final CLOSE retry. Use the position id as
      // a stable ticket fallback when no live position ticket remains.
      position_ticket=(ulong)position_id;
     }

   double entry_price=PositionInitialEntry(position_id);
   double risk_cash=PositionInitialRiskCash(position_id);
   double realized_r=(risk_cash>0.0 ? stage_profit/risk_cash : 0.0);
   string event_id="PARTIAL-"+(string)position_id+"-"+(string)deal_ticket;
   long event_time_ms=(long)HistoryDealGetInteger(deal_ticket,DEAL_TIME_MSC);
   if(event_time_ms<=0)
      event_time_ms=(long)HistoryDealGetInteger(deal_ticket,DEAL_TIME)*1000;

   // ticket = broker position identity; deal_id = exact realized exit deal.
   // destination NONE is deliberate: the backend resolves the canonical signal
   // row and reuses its original FREE/VIP destination + Telegram reply chain.
   if(!g_api.TradeEvent(
         "UPDATE",(string)position_ticket,signal_id,symbol,direction,
         closed_volume,entry_price,sl,tp,exit_price,stage_profit,"",event_id,"NONE",
         gross_profit,commission,swap,0.0,risk_cash,realized_r,
         (string)position_id,(string)deal_ticket,"","MARKET",0,"PARTIAL",event_time_ms))
     {
      Print("NEXUS PARTIAL TRUTH DELIVERY FAILED | signal=",signal_id,
            " position=",(string)position_id," deal=",(string)deal_ticket,
            " error=",g_api.LastError());
      return false;
     }

   Print("NEXUS PARTIAL TRUTH SENT | signal=",signal_id,
         " position=",(string)position_id," deal=",(string)deal_ticket,
         " closed=",DoubleToString(closed_volume,8),
         " net=",DoubleToString(stage_profit,2));
   return true;
  }

void NexusPartialTruthRecoverRecent()
  {
   if(g_partial_truth_recovery_done) return;
   g_partial_truth_recovery_done=true;

   // Recover a missed partial event after terminal/EA restart only while the
   // position is still open. Fully closed positions are reconciled by the core
   // final-CLOSE path and must not receive stale ACTIVE partial messages later.
   datetime now=TimeCurrent();
   datetime from=now-MathMax(1,InpHistoryReconcileHours)*3600;
   if(!HistorySelect(from,now)) return;

   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
     {
      ulong deal=HistoryDealGetTicket(i);
      long position_id=0;
      if(!NexusPartialTruthDealIsExit(deal,position_id)) continue;
      ulong position_ticket=0;
      if(!NexusPartialTruthPositionStillExists(position_id,position_ticket)) continue;
      if(NexusPartialTruthSignalId(position_id)=="") continue;
      NexusPartialTruthQueue(position_id,deal);
     }
  }

void NexusPartialTruthProcessPending()
  {
   NexusPartialTruthRecoverRecent();
   datetime now=TimeCurrent();
   for(int i=ArraySize(g_partial_truth_pending)-1;i>=0;i--)
     {
      if(now<g_partial_truth_pending[i].next_try) continue;
      if(NexusPartialTruthSend(g_partial_truth_pending[i].position_id,
                              g_partial_truth_pending[i].deal_ticket))
        {
         NexusPartialTruthRemove(i);
         continue;
        }

      g_partial_truth_pending[i].attempts++;
      int delay=(int)MathMin(60.0,MathPow(2.0,MathMin(g_partial_truth_pending[i].attempts,5)));
      g_partial_truth_pending[i].next_try=now+delay;
     }
  }

#endif

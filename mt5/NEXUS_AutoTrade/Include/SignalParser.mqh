#ifndef NEXUS_SIGNAL_PARSER_MQH
#define NEXUS_SIGNAL_PARSER_MQH

#include "NexusTypes.mqh"
#include "JsonLite.mqh"

class CNexusSignalParser
  {
private:
   void Defaults(NexusSignal &s)
     {
      s.db_id=0; s.signal_id=""; s.market=""; s.symbol=""; s.direction=""; s.order_type="MARKET"; s.timeframe="M5";
      s.entry=0; s.stop_limit_price=0; s.sl=0; s.tp1=0; s.tp2=0; s.tp3=0; s.tp4=0; s.tp5=0; s.tp6=0; s.tp7=0; s.tp8=0; s.tp9=0; s.tp10=0;
      s.has_tp1=false; s.has_tp2=false; s.has_tp3=false; s.has_tp4=false; s.has_tp5=false; s.has_tp6=false; s.has_tp7=false; s.has_tp8=false; s.has_tp9=false; s.has_tp10=false;
      s.risk_percent=0; s.volume_mode="RISK"; s.lot_size=0; s.has_lot_size=false;
      s.trailing_code=""; s.max_entry_deviation_pct=0; s.has_max_entry_deviation_pct=false; s.max_entry_deviation_abs=0; s.has_max_entry_deviation_abs=false;
      s.break_even_r=1.0; s.trail_step_r=0.5; s.lock_step_r=0.3;
      s.atr_period=14; s.atr_multiplier=2.0; s.activation_r=1.0;
      s.tp1_close_pct=30; s.tp2_close_pct=30; s.runner_pct=40;
      s.swing_left=2; s.swing_right=2;
     }

   bool ParseOne(const string obj,NexusSignal &s)
     {
      Defaults(s);
      s.db_id=NexusJsonLong(obj,"id",0);
      s.signal_id=NexusJsonString(obj,"signal_id","");
      s.market=NexusJsonString(obj,"market",""); StringToUpper(s.market);
      s.symbol=NexusJsonString(obj,"symbol","");
      s.direction=NexusJsonString(obj,"direction",""); StringToUpper(s.direction);
      s.order_type=NexusJsonString(obj,"order_type","MARKET"); StringToUpper(s.order_type);
      s.timeframe=NexusJsonString(obj,"timeframe","M5"); StringToUpper(s.timeframe);
      s.entry=NexusJsonDouble(obj,"entry",0);
      s.stop_limit_price=NexusJsonDouble(obj,"stop_limit_price",0);
      s.sl=NexusJsonDouble(obj,"sl",0);
      if(!NexusJsonIsNull(obj,"tp1")) { s.tp1=NexusJsonDouble(obj,"tp1",0); s.has_tp1=true; }
      if(!NexusJsonIsNull(obj,"tp2")) { s.tp2=NexusJsonDouble(obj,"tp2",0); s.has_tp2=true; }
      if(!NexusJsonIsNull(obj,"tp3")) { s.tp3=NexusJsonDouble(obj,"tp3",0); s.has_tp3=true; }
      if(!NexusJsonIsNull(obj,"tp4")) { s.tp4=NexusJsonDouble(obj,"tp4",0); s.has_tp4=true; }
      if(!NexusJsonIsNull(obj,"tp5")) { s.tp5=NexusJsonDouble(obj,"tp5",0); s.has_tp5=true; }
      if(!NexusJsonIsNull(obj,"tp6")) { s.tp6=NexusJsonDouble(obj,"tp6",0); s.has_tp6=true; }
      if(!NexusJsonIsNull(obj,"tp7")) { s.tp7=NexusJsonDouble(obj,"tp7",0); s.has_tp7=true; }
      if(!NexusJsonIsNull(obj,"tp8")) { s.tp8=NexusJsonDouble(obj,"tp8",0); s.has_tp8=true; }
      if(!NexusJsonIsNull(obj,"tp9")) { s.tp9=NexusJsonDouble(obj,"tp9",0); s.has_tp9=true; }
      if(!NexusJsonIsNull(obj,"tp10")) { s.tp10=NexusJsonDouble(obj,"tp10",0); s.has_tp10=true; }
      s.risk_percent=NexusJsonDouble(obj,"risk_percent",0);
      s.volume_mode=NexusJsonString(obj,"volume_mode","RISK"); StringToUpper(s.volume_mode);
      if(!NexusJsonIsNull(obj,"lot_size")) { s.lot_size=NexusJsonDouble(obj,"lot_size",0); s.has_lot_size=s.lot_size>0; }
      s.trailing_code=NexusJsonString(obj,"trailing_code",""); StringToUpper(s.trailing_code);
      if(!NexusJsonIsNull(obj,"max_entry_deviation_pct"))
        {
         s.max_entry_deviation_pct=NexusJsonDouble(obj,"max_entry_deviation_pct",0);
         s.has_max_entry_deviation_pct=true;
        }
      if(!NexusJsonIsNull(obj,"max_entry_deviation_abs"))
        {
         s.max_entry_deviation_abs=NexusJsonDouble(obj,"max_entry_deviation_abs",0);
         s.has_max_entry_deviation_abs=true;
        }
      string cfg=NexusJsonObject(obj,"trailing_config");
      if(cfg!="")
        {
         s.break_even_r=NexusJsonDouble(cfg,"break_even_r",s.break_even_r);
         s.trail_step_r=NexusJsonDouble(cfg,"trail_step_r",s.trail_step_r);
         s.lock_step_r=NexusJsonDouble(cfg,"lock_step_r",s.lock_step_r);
         s.atr_period=NexusJsonDouble(cfg,"atr_period",s.atr_period);
         s.atr_multiplier=NexusJsonDouble(cfg,"atr_multiplier",s.atr_multiplier);
         s.activation_r=NexusJsonDouble(cfg,"activation_r",s.activation_r);
         s.tp1_close_pct=NexusJsonDouble(cfg,"tp1_close_pct",s.tp1_close_pct);
         s.tp2_close_pct=NexusJsonDouble(cfg,"tp2_close_pct",s.tp2_close_pct);
         s.runner_pct=NexusJsonDouble(cfg,"runner_pct",s.runner_pct);
         s.swing_left=NexusJsonDouble(cfg,"swing_left",s.swing_left);
         s.swing_right=NexusJsonDouble(cfg,"swing_right",s.swing_right);
        }
      return s.db_id>0 && s.signal_id!="" && s.symbol!="" && s.entry>0 && s.sl>0;
     }

public:
   bool ParseSignalObject(const string obj,NexusSignal &signal)
     {
      return ParseOne(obj,signal);
     }

   int ParseSignals(const string json,NexusSignal &signals[])
     {
      ArrayResize(signals,0);
      string arr=NexusJsonArray(json,"signals");
      string objects[];
      int count=NexusSplitObjectArray(arr,objects);
      for(int i=0;i<count;i++)
        {
         NexusSignal s;
         if(ParseOne(objects[i],s))
           {
            int n=ArraySize(signals);
            ArrayResize(signals,n+1);
            signals[n]=s;
           }
        }
      return ArraySize(signals);
     }

   int ParseCommands(const string json,NexusCommand &commands[])
     {
      ArrayResize(commands,0);
      string arr=NexusJsonArray(json,"commands");
      string objects[];
      int count=NexusSplitObjectArray(arr,objects);
      for(int i=0;i<count;i++)
        {
         NexusCommand c;
         c.id=NexusJsonLong(objects[i],"id",0);
         c.signal_db_id=NexusJsonLong(objects[i],"signal_db_id",0);
         c.signal_id=NexusJsonString(objects[i],"signal_id","");
         c.command=NexusJsonString(objects[i],"command",""); StringToUpper(c.command);
         c.payload_value="";
         string payload=NexusJsonObject(objects[i],"payload");
         if(payload!="") c.payload_value=NexusJsonString(payload,"value","");
         if(c.id>0 && c.command!="")
           {
            int n=ArraySize(commands);
            ArrayResize(commands,n+1);
            commands[n]=c;
           }
        }
      return ArraySize(commands);
     }
  };

#endif

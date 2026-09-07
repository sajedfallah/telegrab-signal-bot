#ifndef NEXUS_TYPES_MQH
#define NEXUS_TYPES_MQH


enum ENUM_NEXUS_TRAILING_PROFILE
  {
   NEXUS_TRAIL_01 = 1,
   NEXUS_TRAIL_02 = 2,
   NEXUS_TRAIL_03 = 3,
   NEXUS_TRAIL_04 = 4,
   NEXUS_TRAIL_05 = 5,
   NEXUS_TRAIL_06 = 6,
   NEXUS_TRAIL_07 = 7
  };

enum ENUM_NEXUS_RISK_MODE
  {
   NEXUS_RISK_USER_FIXED_LOT = 0,
   NEXUS_RISK_USER_PERCENT   = 1,
   NEXUS_RISK_SIGNAL_PERCENT = 2
  };

struct NexusSignal
  {
   long   db_id;
   string signal_id;
   string market;
   string symbol;
   string direction;
   string order_type;
   string timeframe;
   double entry;
   double stop_limit_price;
   double sl;
   double tp1;
   double tp2;
   double tp3;
   double tp4;
   double tp5;
   double tp6;
   double tp7;
   double tp8;
   double tp9;
   double tp10;
   bool   has_tp1;
   bool   has_tp2;
   bool   has_tp3;
   bool   has_tp4;
   bool   has_tp5;
   bool   has_tp6;
   bool   has_tp7;
   bool   has_tp8;
   bool   has_tp9;
   bool   has_tp10;
   double risk_percent;
   string volume_mode;
   double lot_size;
   bool   has_lot_size;
   string trailing_code;
   double max_entry_deviation_pct;
   bool   has_max_entry_deviation_pct;
   double max_entry_deviation_abs;
   bool   has_max_entry_deviation_abs;

   // Snapshot values delivered by Backend. Defaults are used if absent.
   double break_even_r;
   double trail_step_r;
   double lock_step_r;
   double atr_period;
   double atr_multiplier;
   double activation_r;
   double tp1_close_pct;
   double tp2_close_pct;
   double runner_pct;
   double swing_left;
   double swing_right;
  };

struct NexusCommand
  {
   long   id;
   long   signal_db_id;
   string signal_id;
   string command;
   string payload_value;
  };

int NexusTrailingModeNumber(const string code)
  {
   if(code=="NEXUS_TRAIL_01") return 1;
   if(code=="NEXUS_TRAIL_02") return 2;
   if(code=="NEXUS_TRAIL_03") return 3;
   if(code=="NEXUS_TRAIL_04") return 4;
   if(code=="NEXUS_TRAIL_05") return 5;
   if(code=="NEXUS_TRAIL_06") return 6;
   if(code=="NEXUS_TRAIL_07") return 7;
   return 0;
  }

string NexusTrailingCode(const int mode)
  {
   return StringFormat("NEXUS_TRAIL_%02d",mode);
  }

#endif

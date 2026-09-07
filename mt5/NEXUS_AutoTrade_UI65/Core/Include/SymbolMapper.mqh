#ifndef NEXUS_SYMBOL_MAPPER_MQH
#define NEXUS_SYMBOL_MAPPER_MQH

// NEXUS Broker Symbol Mapper
//
// Goal:
// A NEXUS signal uses canonical symbols such as XAUUSD, EURUSD, GBPJPY, etc.
// Brokers are free to expose those symbols with prefixes/suffixes such as:
//   XAUUSD.EC
//   XAUUSDm
//   m.XAUUSD
//   XAUUSD-pro
//   GOLD
//   GOLD.EC
//
// This resolver scans ALL symbols offered by the terminal, scores the best
// canonical match, selects it into Market Watch and verifies that it can be
// traded before returning it.

class CNexusSymbolMapper
  {
private:
   string Canonical(string value)
     {
      StringToUpper(value);

      string out="";
      for(int i=0;i<StringLen(value);i++)
        {
         ushort c=StringGetCharacter(value,i);
         if((c>='A' && c<='Z') || (c>='0' && c<='9'))
            out+=ShortToString(c);
        }

      // Common broker aliases.
      if(out=="GOLD" || StringFind(out,"GOLD")==0)
         return "XAUUSD";
      if(out=="SILVER" || StringFind(out,"SILVER")==0)
         return "XAGUSD";

      return out;
     }

   bool IsTradable(const string symbol)
     {
      if(!SymbolSelect(symbol,true))
         return false;

      long trade_mode=(long)SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE);
      if(trade_mode==SYMBOL_TRADE_MODE_DISABLED)
         return false;

      // A broker may expose a symbol but not have a current quote yet.
      // We still accept it when trading is enabled; the TradeManager will
      // reject execution later if a usable Bid/Ask is unavailable.
      return true;
     }

   int MatchScore(const string requested_canonical,const string candidate)
     {
      string c=Canonical(candidate);
      if(c=="") return -1;

      // Exact canonical symbol is always best.
      if(c==requested_canonical)
         return 10000;

      // Broker suffix: XAUUSD.EC -> XAUUSDEC after canonicalization.
      if(StringFind(c,requested_canonical)==0)
        {
         int extra=StringLen(c)-StringLen(requested_canonical);
         return 9000-MathMin(extra,500);
        }

      // Broker prefix: m.XAUUSD -> MXAUUSD after canonicalization.
      int pos=StringFind(c,requested_canonical);
      if(pos>0)
        {
         int extra=StringLen(c)-StringLen(requested_canonical);
         return 8000-MathMin(extra,500)-MathMin(pos,100);
        }

      // Reverse-prefix fallback for uncommon canonical aliases.
      if(StringFind(requested_canonical,c)==0)
         return 6500-MathMin(StringLen(requested_canonical)-StringLen(c),500);

      // Gold/silver semantic aliases.
      if(requested_canonical=="XAUUSD")
        {
         string upper=candidate;
         StringToUpper(upper);
         if(StringFind(upper,"GOLD")>=0)
            return 7000;
         if(StringFind(c,"XAU")>=0 && StringFind(c,"USD")>=0)
            return 6800;
        }
      if(requested_canonical=="XAGUSD")
        {
         string upper=candidate;
         StringToUpper(upper);
         if(StringFind(upper,"SILVER")>=0)
            return 7000;
         if(StringFind(c,"XAG")>=0 && StringFind(c,"USD")>=0)
            return 6800;
        }

      return -1;
     }

public:
   string Resolve(const string requested,const bool allow_mapping=true)
     {
      // First try the exact broker symbol.
      if(IsTradable(requested))
         return requested;

      if(!allow_mapping)
         return "";

      string want=Canonical(requested);
      if(want=="")
         return "";

      string best="";
      int best_score=-1;
      int best_matches=0;

      // false = all symbols known by the terminal, including symbols not yet
      // selected in Market Watch. Selection is performed only after a candidate
      // is validated, so discovery is broker-wide rather than Market-Watch-only.
      int total=SymbolsTotal(false);

      for(int i=0;i<total;i++)
        {
         string candidate=SymbolName(i,false);
         if(candidate=="")
            continue;

         int score=MatchScore(want,candidate);
         if(score<0 || score<best_score)
            continue;

         if(!IsTradable(candidate))
            continue;

         if(score>best_score)
           {
            best=candidate;
            best_score=score;
            best_matches=1;
           }
         else if(score==best_score)
           {
            best_matches++;
           }

         // Exact canonical match cannot be improved. If multiple exact matches
         // somehow exist, return ambiguity instead of guessing.
         if(best_score>=10000 && best_matches>1)
            return "";
        }

      if(best=="" || best_matches>1)
         return "";
      return best;
     }
  };

#endif

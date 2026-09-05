#ifndef NEXUS_API_CLIENT_MQH
#define NEXUS_API_CLIENT_MQH

#include "JsonLite.mqh"


string NexusUrlEncode(const string value)
  {
   uchar bytes[];
   int copied=StringToCharArray(value,bytes,0,WHOLE_ARRAY,CP_UTF8);
   if(copied<=0) return "";
   string out="";
   for(int i=0;i<copied-1;i++)
     {
      int c=(int)bytes[i];
      bool safe=((c>='A' && c<='Z') || (c>='a' && c<='z') || (c>='0' && c<='9') ||
                 c=='-' || c=='_' || c=='.' || c=='~');
      if(safe) out+=CharToString((uchar)c);
      else out+=StringFormat("%%%02X",c);
     }
   return out;
  }

class CNexusAPIClient
  {
private:
   string m_base;
   string m_license;
   string m_account;
   string m_version;
   int    m_timeout;
   int    m_last_http;
   string m_last_error;
   string m_last_response;
   bool   m_admin_mode;
   string m_admin_token;

   string NormalizeBase(string value)
     {
      while(StringLen(value)>0 && StringSubstr(value,StringLen(value)-1,1)=="/")
         value=StringSubstr(value,0,StringLen(value)-1);
      return value;
     }

   bool Request(const string method,const string path,const string body,const bool auth_headers,string &response,const bool terminal_headers=false)
     {
      string url=m_base+path;
      string headers="Content-Type: application/json\r\nAccept: application/json\r\n";
      if(auth_headers)
        {
         headers+="X-License-Key: "+m_license+"\r\n";
         headers+="X-MT5-Account: "+m_account+"\r\n";
         headers+="X-EA-Version: "+m_version+"\r\n";
         if(m_admin_mode)
           {
            headers+="X-NEXUS-Admin-Mode: true\r\n";
            headers+="X-NEXUS-Admin-Token: "+m_admin_token+"\r\n";
           }
         if(terminal_headers)
           {
            headers+="X-Broker: "+AccountInfoString(ACCOUNT_COMPANY)+"\r\n";
            headers+="X-Server: "+AccountInfoString(ACCOUNT_SERVER)+"\r\n";
           }
        }
      char data[];
      char result[];
      string result_headers="";
      if(body!="")
        {
         int copied=StringToCharArray(body,data,0,WHOLE_ARRAY,CP_UTF8);
         if(copied>0) ArrayResize(data,copied-1); // exclude trailing NUL from JSON body
        }
      else ArrayResize(data,0);
      ResetLastError();
      m_last_http=WebRequest(method,url,headers,m_timeout,data,result,result_headers);
      if(m_last_http==-1)
        {
         m_last_error="WebRequest failed: "+IntegerToString(GetLastError())+". Add API URL to MT5 Tools > Options > Expert Advisors > Allow WebRequest.";
         response="";
         m_last_response="";
         return false;
        }
      response=CharArrayToString(result,0,-1,CP_UTF8);
      m_last_response=response;
      if(m_last_http<200 || m_last_http>=300)
        {
         string detail=NexusJsonString(response,"detail",response);
         m_last_error="HTTP "+IntegerToString(m_last_http)+": "+detail;
         return false;
        }
      m_last_error="";
      return true;
     }

   string AuthBody(const bool include_terminal=true)
     {
      string broker=NexusJsonEscape(AccountInfoString(ACCOUNT_COMPANY));
      string server=NexusJsonEscape(AccountInfoString(ACCOUNT_SERVER));
      string body="{\"license_key\":\""+NexusJsonEscape(m_license)+"\",\"account_number\":\""+NexusJsonEscape(m_account)+"\"";
      if(include_terminal)
         body+=",\"broker\":\""+broker+"\",\"server\":\""+server+"\",\"ea_version\":\""+NexusJsonEscape(m_version)+"\"";
      else
         body+=",\"ea_version\":\""+NexusJsonEscape(m_version)+"\"";
      body+="}";
      return body;
     }

public:
   CNexusAPIClient():m_base(""),m_license(""),m_account(""),m_version(""),m_timeout(5000),m_last_http(0),m_last_error(""),m_last_response(""),m_admin_mode(false),m_admin_token("") {}

   void Configure(const string base_url,const string license_key,const string account,const string version,const int timeout_ms)
     {
      m_base=NormalizeBase(base_url);
      m_license=license_key;
      m_account=account;
      m_version=version;
      m_timeout=MathMax(1000,timeout_ms);
      m_admin_mode=false;
      m_admin_token="";
     }

   void ConfigureAdmin(const string base_url,const string account,const string version,const int timeout_ms,const string admin_token)
     {
      m_base=NormalizeBase(base_url); m_license=""; m_account=account; m_version=version;
      m_timeout=MathMax(1000,timeout_ms); m_admin_mode=true; m_admin_token=admin_token;
     }

   string LastError() const { return m_last_error; }
   int LastHttpStatus() const { return m_last_http; }

   bool Activate(string &response)
     {
      return Request("GET","/api/v1/autotrade/activate","",true,response,true);
     }

   bool CheckLicense(string &response)
     {
      return Request("GET","/api/v1/autotrade/license/check","",true,response);
     }

   bool Heartbeat(string &response)
     {
      return Request("GET","/api/v1/autotrade/heartbeat","",true,response);
     }

   bool IssueAdminSignal(const string market_type,const string symbol,const string direction,const string order_type,
                         const string timeframe,const double entry,const double sl,const string targets_json,
                         const double risk_percent,const string volume_mode,const double lot_size,
                         const string trailing_code,const double max_dev_pct,const double max_dev_abs,
                         const string destination,const string request_id,string &response,const string chart_base64="")
     {
      string body=StringFormat("{\"market_type\":\"%s\",\"symbol\":\"%s\",\"direction\":\"%s\",\"order_type\":\"%s\",\"timeframe\":\"%s\",\"entry_price\":%s,\"stop_loss\":%s,\"targets\":[%s],\"risk_percent\":%s,\"volume_mode\":\"%s\",\"lot_size\":%s,\"trailing_code\":%s,\"max_entry_deviation_pct\":%s,\"max_entry_deviation_abs\":%s,\"destination\":\"%s\",\"request_id\":\"%s\",\"chart_base64\":%s}",
         NexusJsonEscape(market_type),NexusJsonEscape(symbol),NexusJsonEscape(direction),NexusJsonEscape(order_type),NexusJsonEscape(timeframe),
         DoubleToString(entry,8),DoubleToString(sl,8),targets_json,DoubleToString(risk_percent,8),NexusJsonEscape(volume_mode),
         lot_size<=0?"null":DoubleToString(lot_size,8),trailing_code==""?"null":"\""+NexusJsonEscape(trailing_code)+"\"",
         max_dev_pct<0?"null":DoubleToString(max_dev_pct,8),max_dev_abs<0?"null":DoubleToString(max_dev_abs,8),NexusJsonEscape(destination),NexusJsonEscape(request_id),
         chart_base64==""?"null":"\""+NexusJsonEscape(chart_base64)+"\"");
      return Request("POST","/api/v1/admin/mt5/signals",body,true,response);
     }


   bool IssueAdminCommand(const long signal_db_id,const string command,const string value,const string request_id,string &response)
     {
      string body=StringFormat("{\"command\":\"%s\",\"value\":%s,\"request_id\":\"%s\"}",
         NexusJsonEscape(command), value==""?"null":"\""+NexusJsonEscape(value)+"\"", NexusJsonEscape(request_id));
      return Request("POST",StringFormat("/api/v1/admin/mt5/signals/%I64d/command",signal_db_id),body,true,response);
     }


   bool GetSignals(const long after_id,const int limit,string &response)
     {
      string path=StringFormat("/api/v1/autotrade/signals?after_id=%I64d&limit=%d",after_id,limit);
      return Request("GET",path,"",true,response);
     }

   bool GetCommands(const long after_id,const int limit,string &response)
     {
      string path=StringFormat("/api/v1/autotrade/commands?after_id=%I64d&limit=%d",after_id,limit);
      return Request("GET",path,"",true,response);
     }

   bool SignalReceipt(const long signal_db_id,const string status,const string ticket,const string error_text)
     {
      // GET is the primary receipt transport for MT5 localhost compatibility.
      // The endpoint is idempotent and authenticated entirely by headers.
      string path=StringFormat("/api/v1/autotrade/signal-receipt?signal_db_id=%I64d&status=%s",signal_db_id,NexusUrlEncode(status));
      if(ticket!="") path+="&ticket="+NexusUrlEncode(ticket);
      if(error_text!="") path+="&error="+NexusUrlEncode(error_text);
      string response;
      if(Request("GET",path,"",true,response)) return true;
      string body=StringFormat("{\"license_key\":\"%s\",\"account_number\":\"%s\",\"signal_db_id\":%I64d,\"status\":\"%s\",\"ticket\":%s,\"error\":%s}",
         NexusJsonEscape(m_license),NexusJsonEscape(m_account),signal_db_id,NexusJsonEscape(status),
         ticket==""?"null":"\""+NexusJsonEscape(ticket)+"\"",
         error_text==""?"null":"\""+NexusJsonEscape(error_text)+"\"");
      if(Request("POST","/api/v1/autotrade/signal-receipt",body,true,response)) return true;
      Print("NEXUS SIGNAL RECEIPT FAILED: signal=",(string)signal_db_id," status=",status," HTTP=",m_last_http," error=",m_last_error);
      return false;
     }

   bool NextChartCaptureJob(string &response)
     {
      return Request("GET","/api/v1/autotrade/admin/chart-capture/jobs/next","",true,response);
     }

   bool UploadChartCapture(const long job_id,const long signal_db_id,const string signal_code,
                           const string broker_symbol,const string timeframe,const string chart_base64,
                           const string captured_at,const string sha256,string &response)
     {
      string body=StringFormat("{\"job_id\":%I64d,\"signal_db_id\":%I64d,\"signal_code\":\"%s\",\"account_number\":\"%s\",\"broker_symbol\":\"%s\",\"timeframe\":\"%s\",\"chart_base64\":\"%s\",\"capture_timestamp\":\"%s\",\"image_sha256\":\"%s\"}",
         job_id,signal_db_id,NexusJsonEscape(signal_code),NexusJsonEscape(m_account),NexusJsonEscape(broker_symbol),
         NexusJsonEscape(timeframe),NexusJsonEscape(chart_base64),NexusJsonEscape(captured_at),NexusJsonEscape(sha256));
      return Request("POST",StringFormat("/api/v1/autotrade/admin/chart-capture/%I64d/result",job_id),body,true,response);
     }

   bool FailChartCapture(const long job_id,const string error_code,const string error_text,string &response)
     {
      string body=StringFormat("{\"job_id\":%I64d,\"account_number\":\"%s\",\"error_code\":\"%s\",\"error_text\":\"%s\"}",
         job_id,NexusJsonEscape(m_account),NexusJsonEscape(error_code),NexusJsonEscape(error_text));
      return Request("POST",StringFormat("/api/v1/autotrade/admin/chart-capture/%I64d/fail",job_id),body,true,response);
     }

   bool LiveState(const string positions_json,const string orders_json,string &response)
     {
      string body=StringFormat("{\"license_key\":\"%s\",\"account_number\":\"%s\",\"broker\":\"%s\",\"server\":\"%s\",\"ea_version\":\"%s\",\"positions\":[%s],\"orders\":[%s]}",
         NexusJsonEscape(m_license),NexusJsonEscape(m_account),NexusJsonEscape(AccountInfoString(ACCOUNT_COMPANY)),
         NexusJsonEscape(AccountInfoString(ACCOUNT_SERVER)),NexusJsonEscape(m_version),positions_json,orders_json);
      return Request("POST","/api/v1/autotrade/live-state",body,true,response,true);
     }


   string LastResponse() const { return m_last_response; }

   bool TradeEvent(const string event_name,const string ticket,const string signal_id,const string symbol,const string direction,
                   const double volume,const double entry_price,const double stop_loss,const double take_profit,
                   const double exit_price,const double profit,const string chart_base64,
                   const string event_id="",const string destination="BOTH",
                   const double gross_profit=0,const double commission=0,const double swap=0,
                   const double slippage=0,const double risk_cash=0,const double realized_r=0,
                   const string position_id="",const string deal_id="",const string cycle_id="",const string order_type="MARKET",
                   const double stop_limit_price=0,const string close_reason="",const long event_time_ms=0)
     {
      string body=StringFormat(
         "{\"license_key\":\"%s\",\"account_number\":\"%s\",\"event\":\"%s\",\"ticket\":\"%s\",\"signal_id\":\"%s\",\"symbol\":\"%s\",\"direction\":\"%s\",\"volume\":%s,\"entry_price\":%s,\"stop_loss\":%s,\"take_profit\":%s,\"exit_price\":%s,\"profit\":%s,\"gross_profit\":%s,\"commission\":%s,\"swap\":%s,\"slippage\":%s,\"risk_cash\":%s,\"realized_r\":%s,\"position_id\":\"%s\",\"deal_id\":\"%s\",\"cycle_id\":\"%s\",\"chart_base64\":\"%s\",\"event_id\":\"%s\",\"destination\":\"%s\",\"order_type\":\"%s\",\"stop_limit_price\":%s,\"close_reason\":\"%s\",\"event_time_ms\":%I64d}",
         NexusJsonEscape(m_license),NexusJsonEscape(m_account),NexusJsonEscape(event_name),
         NexusJsonEscape(ticket),NexusJsonEscape(signal_id),NexusJsonEscape(symbol),NexusJsonEscape(direction),
         DoubleToString(volume,8),DoubleToString(entry_price,8),DoubleToString(stop_loss,8),
         DoubleToString(take_profit,8),DoubleToString(exit_price,8),DoubleToString(profit,8),
         DoubleToString(gross_profit,8),DoubleToString(commission,8),DoubleToString(swap,8),
         DoubleToString(slippage,8),DoubleToString(risk_cash,8),DoubleToString(realized_r,8),
         NexusJsonEscape(position_id),NexusJsonEscape(deal_id),NexusJsonEscape(cycle_id),
         NexusJsonEscape(chart_base64),NexusJsonEscape(event_id),NexusJsonEscape(destination),
         NexusJsonEscape(order_type),DoubleToString(stop_limit_price,8),NexusJsonEscape(close_reason),event_time_ms);
      string response;
      return Request("POST","/api/v1/autotrade/trade-event",body,true,response);
     }


   bool HistoryReconcile(const string json_items)
     {
      string body=StringFormat("{\"license_key\":\"%s\",\"account_number\":\"%s\",\"items\":[%s]}",
                              NexusJsonEscape(m_license),NexusJsonEscape(m_account),json_items);
      string response;
      return Request("POST","/api/v1/autotrade/history-reconcile",body,true,response,true);
     }

   bool CommandReceipt(const long command_id,const string status,const string error_text)
     {
      string body=StringFormat("{\"license_key\":\"%s\",\"account_number\":\"%s\",\"command_id\":%I64d,\"status\":\"%s\",\"error\":%s}",
                               NexusJsonEscape(m_license),NexusJsonEscape(m_account),command_id,NexusJsonEscape(status),
                               error_text==""?"null":"\""+NexusJsonEscape(error_text)+"\"");
      string response;
      return Request("POST","/api/v1/autotrade/command-receipt",body,true,response);
     }
  };

#endif

param(
    [Parameter(Mandatory=$true)]
    [string]$SourcePath
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SourcePath)) {
    throw "ChartAgent source not found: $SourcePath"
}

$SourcePath = (Resolve-Path $SourcePath).Path
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = "$SourcePath.v24-backup-$Stamp"
Copy-Item $SourcePath $Backup -Force

$src = Get-Content $SourcePath -Raw -Encoding UTF8
$original = $src

Write-Host "=== NEXUS ChartAgent V24 Reliability Patch ==="
Write-Host "Source :" $SourcePath
Write-Host "Backup :" $Backup

# Always stamp the version so runtime logs prove which reliability contract is loaded.
$src = [regex]::Replace(
    $src,
    '#define\s+NEXUS_CHART_AGENT_VERSION\s+"[^"]+"',
    '#define NEXUS_CHART_AGENT_VERSION "0.6.5-chart-agent-reliability-v24"',
    1
)

$fitReplacement = @'
bool FitTradeLevelsToChart(const long chart_id,
                           const double entry,
                           const double sl,
                           const double &targets[])
{
   g_last_scale_error="";

   double chart_min=0.0;
   double chart_max=0.0;
   bool chart_min_ok=ChartGetDouble(chart_id,CHART_PRICE_MIN,0,chart_min);
   bool chart_max_ok=ChartGetDouble(chart_id,CHART_PRICE_MAX,0,chart_max);

   double required_min=MathMin(entry,sl);
   double required_max=MathMax(entry,sl);
   for(int i=0;i<ArraySize(targets);i++)
   {
      if(targets[i]<=0.0) continue;
      required_min=MathMin(required_min,targets[i]);
      required_max=MathMax(required_max,targets[i]);
   }

   if(required_min<=0.0 || required_max<=required_min)
   {
      g_last_scale_error="INVALID_REQUIRED_RANGE:min="+DoubleToString(required_min,2)+
                         ",max="+DoubleToString(required_max,2);
      return false;
   }

   // A newly opened/off-screen chart can report 0/0 while its pixels are still
   // valid. Never use 0/0 as authoritative input for the required trade range.
   if(chart_min_ok && chart_max_ok && chart_max>chart_min && chart_min>0.0)
   {
      required_min=MathMin(required_min,chart_min);
      required_max=MathMax(required_max,chart_max);
   }
   else
   {
      DiagTrace("SCALE_RANGE_FALLBACK min="+DoubleToString(required_min,2)+
                " max="+DoubleToString(required_max,2));
   }

   double span=required_max-required_min;
   if(span<=0.0) span=MathMax(MathAbs(required_max)*0.01,1.0);
   double padding=MathMax(span*0.08,1.0);
   double fixed_min=required_min-padding;
   double fixed_max=required_max+padding;

   ResetLastError();
   if(!ChartSetInteger(chart_id,CHART_SCALEFIX,true))
   {
      g_last_scale_error="SCALEFIX_SET_FAILED:err="+IntegerToString(GetLastError());
      return false;
   }
   if(!ChartSetDouble(chart_id,CHART_FIXED_MIN,fixed_min))
   {
      g_last_scale_error="FIXED_MIN_SET_FAILED:err="+IntegerToString(GetLastError());
      return false;
   }
   if(!ChartSetDouble(chart_id,CHART_FIXED_MAX,fixed_max))
   {
      g_last_scale_error="FIXED_MAX_SET_FAILED:err="+IntegerToString(GetLastError());
      return false;
   }

   // Stable-range verification: the terminal may need several redraw cycles
   // before CHART_PRICE_MIN/MAX reflect CHART_FIXED_MIN/MAX.
   ulong verify_start=GetTickCount64();
   double visible_min=0.0;
   double visible_max=0.0;
   while(GetTickCount64()-verify_start < 2200)
   {
      ChartRedraw(chart_id);
      Sleep(200);

      bool visible_min_ok=ChartGetDouble(chart_id,CHART_PRICE_MIN,0,visible_min);
      bool visible_max_ok=ChartGetDouble(chart_id,CHART_PRICE_MAX,0,visible_max);
      if(visible_min_ok && visible_max_ok && visible_max>visible_min &&
         visible_min<=required_min && visible_max>=required_max)
      {
         DiagTrace("SCALE_VISIBLE_RANGE_CONFIRMED visible_min="+DoubleToString(visible_min,2)+
                   " visible_max="+DoubleToString(visible_max,2));
         return true;
      }

      double read_fixed_min=0.0;
      double read_fixed_max=0.0;
      bool fixed_min_ok=ChartGetDouble(chart_id,CHART_FIXED_MIN,0,read_fixed_min);
      bool fixed_max_ok=ChartGetDouble(chart_id,CHART_FIXED_MAX,0,read_fixed_max);
      if(fixed_min_ok && fixed_max_ok && read_fixed_max>read_fixed_min &&
         read_fixed_min<=required_min && read_fixed_max>=required_max)
      {
         DiagTrace("SCALE_FIXED_RANGE_CONFIRMED fixed_min="+DoubleToString(read_fixed_min,2)+
                   " fixed_max="+DoubleToString(read_fixed_max,2)+
                   " visible_min="+DoubleToString(visible_min,2)+
                   " visible_max="+DoubleToString(visible_max,2));
         return true;
      }
   }

   // Last-resort visual fallback: restore terminal autoscale and accept only a
   // real non-zero visible range. This produces a usable broker chart instead
   // of a false 0/0 hard failure, while never fabricating prices.
   ChartSetInteger(chart_id,CHART_SCALEFIX,false);
   ChartRedraw(chart_id);
   Sleep(450);
   visible_min=0.0;
   visible_max=0.0;
   if(ChartGetDouble(chart_id,CHART_PRICE_MIN,0,visible_min) &&
      ChartGetDouble(chart_id,CHART_PRICE_MAX,0,visible_max) &&
      visible_max>visible_min && visible_min>0.0)
   {
      DiagTrace("SCALE_AUTOSCALE_FALLBACK visible_min="+DoubleToString(visible_min,2)+
                " visible_max="+DoubleToString(visible_max,2));
      return true;
   }

   g_last_scale_error="RANGE_VERIFY_FAILED"+
      StringFormat(":visible_min=%.2f,visible_max=%.2f,required_min=%.2f,required_max=%.2f,fixed_min=%.2f,fixed_max=%.2f",
                   visible_min,visible_max,required_min,required_max,fixed_min,fixed_max);
   return false;
}
bool DrawCompactTag
'@

$fitPattern = '(?s)bool FitTradeLevelsToChart\(.*?\n\}\s*bool DrawCompactTag'
$fitCount = [regex]::Matches($src, $fitPattern).Count
if ($fitCount -ne 1) {
    throw "FitTradeLevelsToChart patch target count=$fitCount (expected 1)"
}
$src = [regex]::Replace($src, $fitPattern, $fitReplacement, 1)

$postReplacement = @'
bool RetryableHttpStatus(const int status)
{
   return status==0 || status==429 || status==502 || status==503 || status==504;
}

bool PostWithRetry(const string path,const string body,int &status,string &response,const string operation)
{
   const int max_attempts=4;
   for(int attempt=1;attempt<=max_attempts;attempt++)
   {
      status=0;
      response="";
      bool transport_ok=Http("POST",path,body,status,response);
      if(transport_ok && status>=200 && status<300)
      {
         DiagTrace(operation+"_HTTP_OK attempt="+IntegerToString(attempt)+" status="+IntegerToString(status));
         return true;
      }

      int mql_error=g_diag_last_http_error;
      DiagTrace(operation+"_HTTP_RETRY attempt="+IntegerToString(attempt)+
                " status="+IntegerToString(status)+
                " mql_error="+IntegerToString(mql_error));

      if(transport_ok && !RetryableHttpStatus(status))
         return false;
      if(attempt>=max_attempts)
         return false;

      int delay_ms=(int)MathMin(4000,500*MathPow(2,attempt-1));
      Sleep(delay_ms);
   }
   return false;
}

void FailJob(const long job_id,const string error_text)
{
   string body="{\"error_code\":\"CAPTURE_FAILED\",\"error_text\":\""+JsonEscape(error_text)+"\"}";
   int status=0; string response="";
   bool posted=PostWithRetry(
      "/api/v1/autotrade/admin/chart-capture/"+IntegerToString((int)job_id)+"/fail",
      body,status,response,"FAIL_JOB"
   );
   Print("[NEXUS ChartAgent] Job ",job_id," failed: ",error_text,
         " HTTP=",status," posted=",posted ? "1" : "0");
}

void DiagTrace
'@

$postPattern = '(?s)void FailJob\(.*?\n\}\s*\nvoid DiagTrace'
$postCount = [regex]::Matches($src, $postPattern).Count
if ($postCount -ne 1) {
    throw "FailJob patch target count=$postCount (expected 1)"
}
$src = [regex]::Replace($src, $postPattern, $postReplacement, 1)

# Validate screenshot bytes before SHA/base64. Tiny/truncated files must never be
# uploaded as a successful chart result.
$readBlock = @'
      if(!ReadFileBytes(filename,raw))
      {
         error_text="SCREENSHOT_READ_FAILED";
         break;
      }
      if(!HexSha256(raw,sha256))
'@
$readReplacement = @'
      if(!ReadFileBytes(filename,raw))
      {
         error_text="SCREENSHOT_READ_FAILED";
         break;
      }
      if(ArraySize(raw)<4096)
      {
         error_text="SCREENSHOT_TOO_SMALL_BYTES_"+IntegerToString(ArraySize(raw));
         break;
      }
      if(ArraySize(raw)<8 || raw[0]!=0x89 || raw[1]!=0x50 || raw[2]!=0x4E || raw[3]!=0x47 ||
         raw[4]!=0x0D || raw[5]!=0x0A || raw[6]!=0x1A || raw[7]!=0x0A)
      {
         error_text="SCREENSHOT_INVALID_PNG_SIGNATURE";
         break;
      }
      if(!HexSha256(raw,sha256))
'@
if (-not $src.Contains($readBlock)) {
    if ($src -notmatch 'SCREENSHOT_TOO_SMALL_BYTES_') {
        throw "Screenshot validation patch target not found"
    }
} else {
    $src = $src.Replace($readBlock, $readReplacement)
}

$uploadBlock = @'
   status=0; response="";
   if(!Http("POST","/api/v1/autotrade/admin/chart-capture/"+IntegerToString((int)job_id)+"/result",body,status,response))
   {
      Print("[NEXUS ChartAgent] Upload transport failed for job ",job_id);
      return;
   }
   if(status<200 || status>=300)
   {
      Print("[NEXUS ChartAgent] Upload rejected. job=",job_id," HTTP=",status," body=",response);
      return;
   }
   Print("[NEXUS ChartAgent] Screenshot uploaded. job=",job_id," signal=",signal_code," symbol=",broker_symbol);
'@
$uploadReplacement = @'
   status=0; response="";
   if(!PostWithRetry(
         "/api/v1/autotrade/admin/chart-capture/"+IntegerToString((int)job_id)+"/result",
         body,status,response,"UPLOAD_RESULT"))
   {
      Print("[NEXUS ChartAgent] Upload rejected after retries. job=",job_id,
            " HTTP=",status," body=",response);
      return;
   }
   DiagTrace("SCREENSHOT_UPLOAD_CONFIRMED job="+IntegerToString((int)job_id)+
             " sha256="+sha256+
             " base64_chars="+IntegerToString(StringLen(image_b64)));
   Print("[NEXUS ChartAgent] Screenshot uploaded. job=",job_id," signal=",signal_code," symbol=",broker_symbol);
'@
if (-not $src.Contains($uploadBlock)) {
    if ($src -notmatch 'SCREENSHOT_UPLOAD_CONFIRMED') {
        throw "Upload retry patch target not found"
    }
} else {
    $src = $src.Replace($uploadBlock, $uploadReplacement)
}

if ($src -eq $original) {
    throw "No ChartAgent changes were applied"
}

$required = @(
    '0.6.5-chart-agent-reliability-v24',
    'SCALE_VISIBLE_RANGE_CONFIRMED',
    'SCALE_FIXED_RANGE_CONFIRMED',
    'SCALE_AUTOSCALE_FALLBACK',
    'PostWithRetry',
    'SCREENSHOT_TOO_SMALL_BYTES_',
    'SCREENSHOT_UPLOAD_CONFIRMED'
)
foreach ($marker in $required) {
    if (-not $src.Contains($marker)) {
        throw "Required V24 marker missing after patch: $marker"
    }
}

[System.IO.File]::WriteAllText($SourcePath, $src, [System.Text.UTF8Encoding]::new($true))

Write-Host "`nCHART AGENT V24 SOURCE PATCH: PASS"
Write-Host "Compile this MQ5 in MetaEditor and verify 0 errors before deploying the EX5."
Write-Host "Expected runtime version: 0.6.5-chart-agent-reliability-v24"

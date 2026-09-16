param(
    [Parameter(Mandatory=$true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Path)) { throw "ChartAgent source not found: $Path" }

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Text = [System.IO.File]::ReadAllText($Path)

# Idempotent: a second run must not mutate the already-promoted source.
if ($Text -match 'NEXUS_CHART_VISUAL_PROFILE "clean-text-level-v36"') {
    Write-Host "CHART VISUAL V36: ALREADY APPLIED" -ForegroundColor Green
    exit 0
}

$OldVersion = '#define NEXUS_CHART_AGENT_VERSION "0.6.5-chart-agent-inline-v2-diag5-scale-fallback"'
$NewVersion = '#define NEXUS_CHART_AGENT_VERSION "0.6.5-chart-agent-clean-text-v36"'
$OldProfile = '#define NEXUS_CHART_VISUAL_PROFILE "approved-inline-level-v2"'
$NewProfile = '#define NEXUS_CHART_VISUAL_PROFILE "clean-text-level-v36"'

if (-not $Text.Contains($OldVersion)) { throw "Expected ChartAgent version marker not found" }
if (-not $Text.Contains($OldProfile)) { throw "Expected ChartAgent visual profile marker not found" }
$Text = $Text.Replace($OldVersion, $NewVersion).Replace($OldProfile, $NewProfile)

$FunctionStart = $Text.IndexOf('bool DrawCompactTag(')
if ($FunctionStart -lt 0) { throw "DrawCompactTag function not found" }
$BlockStart = $Text.IndexOf('   int height=MathMax(14,InpLabelHeight);', $FunctionStart)
if ($BlockStart -lt 0) { throw "Legacy DrawCompactTag body marker not found" }
$FunctionEndMarker = "`r`n}`r`n`r`nbool HexSha256"
$FunctionEnd = $Text.IndexOf($FunctionEndMarker, $BlockStart)
if ($FunctionEnd -lt 0) {
    $FunctionEndMarker = "`n}`n`nbool HexSha256"
    $FunctionEnd = $Text.IndexOf($FunctionEndMarker, $BlockStart)
}
if ($FunctionEnd -lt 0) { throw "DrawCompactTag end marker not found" }

$NewBody = @'
   // V36: text-only tags. The old solid rectangle labels obscured prices and
   // created four extra chart objects per level. They also made boundary tags
   // (especially TP4) fail the whole screenshot. Keep the colored level ray,
   // render only compact text, and clamp the label to the screenshot viewport.
   int font_size=MathMax(8,InpLabelFontSize);
   int price_font=MathMax(9,InpLabelFontSize+1);
   int safe_margin=MathMax(4,InpLabelRightMargin);
   int edge=MathMax(10,price_font+3);
   center_y=MathMax(edge,MathMin(output_height-edge,center_y));

   string name_text=prefix+key+".NAME.TEXT";
   string price_text=prefix+key+".PRICE.TEXT";

   ResetLastError();
   if(!ObjectCreate(chart_id,name_text,OBJ_LABEL,0,0,0))
   {
      g_last_tag_error="CREATE_NAME_TEXT_FAILED:key="+key+",err="+IntegerToString(GetLastError());
      return false;
   }
   ObjectSetInteger(chart_id,name_text,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
   ObjectSetInteger(chart_id,name_text,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(chart_id,name_text,OBJPROP_XDISTANCE,safe_margin+88);
   ObjectSetInteger(chart_id,name_text,OBJPROP_YDISTANCE,center_y);
   ObjectSetInteger(chart_id,name_text,OBJPROP_COLOR,accent_color);
   ObjectSetInteger(chart_id,name_text,OBJPROP_FONTSIZE,font_size);
   ObjectSetInteger(chart_id,name_text,OBJPROP_BACK,false);
   ObjectSetInteger(chart_id,name_text,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(chart_id,name_text,OBJPROP_SELECTED,false);
   ObjectSetInteger(chart_id,name_text,OBJPROP_HIDDEN,true);
   ObjectSetString(chart_id,name_text,OBJPROP_FONT,"Arial");
   ObjectSetString(chart_id,name_text,OBJPROP_TEXT,caption);

   ResetLastError();
   if(!ObjectCreate(chart_id,price_text,OBJ_LABEL,0,0,0))
   {
      g_last_tag_error="CREATE_PRICE_TEXT_FAILED:key="+key+",err="+IntegerToString(GetLastError());
      ObjectDelete(chart_id,name_text);
      return false;
   }
   ObjectSetInteger(chart_id,price_text,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
   ObjectSetInteger(chart_id,price_text,OBJPROP_ANCHOR,ANCHOR_CENTER);
   ObjectSetInteger(chart_id,price_text,OBJPROP_XDISTANCE,safe_margin+34);
   ObjectSetInteger(chart_id,price_text,OBJPROP_YDISTANCE,center_y);
   ObjectSetInteger(chart_id,price_text,OBJPROP_COLOR,clrWhite);
   ObjectSetInteger(chart_id,price_text,OBJPROP_FONTSIZE,price_font);
   ObjectSetInteger(chart_id,price_text,OBJPROP_BACK,false);
   ObjectSetInteger(chart_id,price_text,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(chart_id,price_text,OBJPROP_SELECTED,false);
   ObjectSetInteger(chart_id,price_text,OBJPROP_HIDDEN,true);
   ObjectSetString(chart_id,price_text,OBJPROP_FONT,"Arial Bold");
   ObjectSetString(chart_id,price_text,OBJPROP_TEXT,
                   DoubleToString(price,MathMax(0,digits)));
   return true;
'@

$Prefix = $Text.Substring(0, $BlockStart)
$Suffix = $Text.Substring($FunctionEnd)
$Text = $Prefix + $NewBody.Replace("`n", [Environment]::NewLine) + $Suffix

[System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)

$Check = [System.IO.File]::ReadAllText($Path)
if ($Check -notmatch 'clean-text-level-v36') { throw "V36 profile verification failed" }
$Start2 = $Check.IndexOf('bool DrawCompactTag(')
$End2 = $Check.IndexOf('bool HexSha256', $Start2)
$TagBody = $Check.Substring($Start2, $End2-$Start2)
if ($TagBody -match 'OBJ_RECTANGLE_LABEL') { throw "V36 failed: rectangle label remains inside DrawCompactTag" }
if ($TagBody -notmatch 'OBJPROP_COLOR,clrWhite') { throw "V36 failed: readable white price marker missing" }
if ($TagBody -notmatch 'MathMax\(edge,MathMin\(output_height-edge,center_y\)\)') { throw "V36 failed: viewport clamp missing" }

Write-Host "CHART VISUAL V36 PATCH: PASS" -ForegroundColor Green
Write-Host "SOURCE:" $Path

param([Parameter(Mandatory)][string]$RunRoot)
$ErrorActionPreference = 'Stop'
$allowedRoot = [IO.Path]::GetFullPath('E:\Projects\PLW\.sandbox\r0') + [IO.Path]::DirectorySeparatorChar
$resolvedRun = (Resolve-Path -LiteralPath $RunRoot).Path
if (-not $resolvedRun.StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Only synthetic R0 runs are allowed.' }
$result = [System.Collections.Generic.List[object]]::new()
$office = New-Object -ComObject PowerPoint.Application
$initialCount = $office.Presentations.Count
try {
  foreach ($name in @('宽屏 合成课件','标准 合成课件')) {
    $source = Join-Path $resolvedRun "sources\$name.pptx"
    $output = Join-Path $resolvedRun "converted\$name.pdf"
    if (Test-Path -LiteralPath $output) { throw 'Refusing to overwrite conversion output.' }
    $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $stamp = (Get-Item -LiteralPath $source).LastWriteTimeUtc.Ticks
    $presentation = $null
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
      $presentation = $office.Presentations.Open($source,-1,0,0)
      # Fixture-only change in memory; readonly source is never saved.
      $presentation.Slides.Item(4).SlideShowTransition.Hidden = -1
      $printRange = $presentation.PrintOptions.Ranges.Add(1,$presentation.Slides.Count)
      $presentation.ExportAsFixedFormat($output,2,1,0,1,1,-1,$printRange,1)
      $exportHeight = [int](1280*$presentation.PageSetup.SlideHeight/$presentation.PageSetup.SlideWidth)
      $presentation.Slides.Item(1).Export((Join-Path $resolvedRun "evidence\$name-original.png"),'PNG',1280,$exportHeight)
      if ($name -eq '宽屏 合成课件') {
        $legacy = Join-Path $resolvedRun 'sources\旧格式 合成课件.ppt'
        if (Test-Path -LiteralPath $legacy) { throw 'Legacy fixture already exists.' }
        $presentation.SaveCopyAs($legacy,1)
      }
      $presentation.Saved = -1
      $result.Add([pscustomobject]@{source=$source;output=$output;slides=$presentation.Slides.Count;elapsed_ms=$timer.ElapsedMilliseconds;source_unchanged=((Get-FileHash -LiteralPath $source).Hash -eq $hash -and (Get-Item -LiteralPath $source).LastWriteTimeUtc.Ticks -eq $stamp)})
    } finally { if ($null -ne $presentation) { $presentation.Close();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) } }
  }
  $legacy = Join-Path $resolvedRun 'sources\旧格式 合成课件.ppt'
  $legacyOutput = Join-Path $resolvedRun 'converted\旧格式 合成课件.pdf'
  $legacyHash = (Get-FileHash -LiteralPath $legacy).Hash
  $presentation = $office.Presentations.Open($legacy,-1,0,0)
  try {
    $printRange = $presentation.PrintOptions.Ranges.Add(1,$presentation.Slides.Count)
    $presentation.ExportAsFixedFormat($legacyOutput,2,1,0,1,1,-1,$printRange,1)
    $result.Add([pscustomobject]@{source=$legacy;output=$legacyOutput;slides=$presentation.Slides.Count;source_unchanged=((Get-FileHash -LiteralPath $legacy).Hash -eq $legacyHash)})
  } finally {$presentation.Close();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation)}
  [pscustomobject]@{initial_presentations=$initialCount;final_presentations=$office.Presentations.Count;files=$result} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $resolvedRun 'conversion.json') -Encoding utf8
  $result | Select-Object slides,elapsed_ms,source_unchanged | ConvertTo-Json
} finally {
  # PowerPoint may be shared with the user's existing window. Never call Quit.
  [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($office)
}

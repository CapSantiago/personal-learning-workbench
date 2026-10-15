param([Parameter(Mandatory)][string]$Source,[Parameter(Mandatory)][string]$Target,
      [ValidateRange(10,180)][int]$TimeoutSeconds=180)
$ErrorActionPreference='Stop'
$inputPath=(Resolve-Path -LiteralPath $Source).Path
$outputPath=[IO.Path]::GetFullPath($Target)
if ([IO.Path]::GetDirectoryName($inputPath) -ne [IO.Path]::GetDirectoryName($outputPath)) { throw 'Export must stay in one isolated job directory.' }
if ($inputPath -notmatch '\\jobs\\[0-9a-f-]{36}\\input\.pptx$' -or [IO.Path]::GetFileName($outputPath) -ne 'animation.mp4') { throw 'Only an isolated PLW job copy may be exported.' }
if (Test-Path -LiteralPath $outputPath) { throw 'Refusing to overwrite video.' }
$before=(Get-FileHash -LiteralPath $inputPath).Hash
$office=New-Object -ComObject PowerPoint.Application
$presentation=$null
$previousSecurity=$office.AutomationSecurity
try {
  # This application can be shared with the user's work. Change its global
  # macro policy only while opening our isolated copy, not during video export.
  try {
    $office.AutomationSecurity=3
    $presentation=$office.Presentations.Open($inputPath,-1,0,0)
  } finally {
    $office.AutomationSecurity=$previousSecurity
  }
  if ($presentation.Slides.Count -gt 300) { throw 'Too many slides for interactive export.' }
  $presentation.CreateVideo($outputPath,$true,5,480,24,60)
  $timer=[Diagnostics.Stopwatch]::StartNew()
  do {
    Start-Sleep -Milliseconds 500
    $state=[int]$presentation.CreateVideoStatus
    if ($state -eq 4) { throw 'PowerPoint video export failed.' }
    if ($timer.Elapsed.TotalSeconds -gt $TimeoutSeconds) { throw 'PLW_MEDIA_EXPORT_TIMEOUT' }
  } while ($state -ne 3)
  if (!(Test-Path -LiteralPath $outputPath) -or (Get-Item -LiteralPath $outputPath).Length -lt 16) { throw 'PowerPoint did not create a video.' }
  if ((Get-FileHash -LiteralPath $inputPath).Hash -ne $before) { throw 'Source changed during export.' }
} finally {
  try {
    if ($null -ne $presentation) {
      try { $presentation.Close() } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) }
    }
  } finally {
    # The application may also contain the user's work. Never Quit or kill Office.
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($office)
  }
}

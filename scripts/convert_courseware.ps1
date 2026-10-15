param([Parameter(Mandatory)][string]$Source,[Parameter(Mandatory)][string]$Target)
$ErrorActionPreference='Stop'
$inputPath=(Resolve-Path -LiteralPath $Source).Path
$outputPath=[IO.Path]::GetFullPath($Target)
if ([IO.Path]::GetDirectoryName($inputPath) -ne [IO.Path]::GetDirectoryName($outputPath)) { throw 'Conversion must stay in one isolated job directory.' }
if ($inputPath -notmatch '\\jobs\\[0-9a-f-]{36}\\input\.(ppt|pptx)$') { throw 'Only an isolated PLW job copy may be converted.' }
if (Test-Path -LiteralPath $outputPath) { throw 'Refusing to overwrite PDF.' }
$before=(Get-FileHash -LiteralPath $inputPath).Hash
$office=New-Object -ComObject PowerPoint.Application
$presentation=$null
$previousSecurity=$office.AutomationSecurity
try {
  # Uploaded courseware must never execute embedded Office macros.
  $office.AutomationSecurity=3
  $presentation=$office.Presentations.Open($inputPath,-1,0,0)
  $range=$presentation.PrintOptions.Ranges.Add(1,$presentation.Slides.Count)
  $presentation.ExportAsFixedFormat($outputPath,2,1,0,1,1,-1,$range,1)
  if ((Get-FileHash -LiteralPath $inputPath).Hash -ne $before) { throw 'Input changed during conversion.' }
} finally {
  try {
    if ($null -ne $presentation) {
      try { $presentation.Close() } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) }
    }
  } finally {
    try { $office.AutomationSecurity=$previousSecurity } finally {
      # This may be the user's running PowerPoint. Never Quit or kill Office.
      [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($office)
    }
  }
}

# The special events' logos (special.html) as PNGs, by headless Microsoft Edge: <key>-logo.png (600 x 340, transparent),
# <key>.png (the tile, 640 x 360) and <key>-banner.png (1200 x 630: the website's page and home strip, Discord).
# Run from this folder: .\render-special.ps1, then copy <key>-logo.png and <key>.png to client/acr_daily/series.
$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
$page = 'file:///' + ((Join-Path $PSScriptRoot 'special.html') -replace '\\', '/')
foreach ($x in @(@('skoda-logo', 600, 340), @('skoda', 640, 360), @('skoda-banner', 1200, 630))) {
  $out = Join-Path $PSScriptRoot ($x[0] + '.png')
  & $edge --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 --virtual-time-budget=8000 `
    "--window-size=$($x[1]),$($x[2])" "--screenshot=$out" "$page`?only=$($x[0])" 2>$null | Out-Null
  Write-Output "$out $((Get-Item $out).Length)"
}

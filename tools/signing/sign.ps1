# Signs the release's programs (release.yml) with ACR Daily's code-signing certificate: Authenticode, SHA-256, with a
# timestamp (so the signature stays valid after the certificate expires). The certificate is a GitHub secret:
#   SIGN_PFX_BASE64    the .pfx, in base64 (tools/signing/new-certificate.ps1 prints it)
#   SIGN_PFX_PASSWORD  its password
# Without them nothing is signed and the build goes on (a fork, a test build). As the gist the user pointed to does it
# (https://gist.github.com/PaulCreusy/7fade8d5a8026f2228a97d31343b335e): signtool sign /f /p /fd SHA256 /tr <timestamp>
# /td SHA256. The password goes to signtool through its argument on the CI runner only (never in a log: it is masked).
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Files)
$ErrorActionPreference = 'Stop'
if (-not $env:SIGN_PFX_BASE64 -or -not $env:SIGN_PFX_PASSWORD) {
  Write-Output 'Not signed: no SIGN_PFX_BASE64 / SIGN_PFX_PASSWORD secret.'
  exit 0
}
$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
  Sort-Object FullName | Select-Object -Last 1
if (-not $signtool) { throw 'signtool.exe not found (Windows SDK)' }
$pfx = Join-Path $env:RUNNER_TEMP 'acrdaily-sign.pfx'
[IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:SIGN_PFX_BASE64))
try {
  foreach ($f in $Files) {
    foreach ($path in (Resolve-Path $f)) {
      $ok = $false
      foreach ($ts in 'http://timestamp.digicert.com', 'http://timestamp.sectigo.com') {   # (a timestamp server down: the next)
        & $signtool.FullName sign /f $pfx /p $env:SIGN_PFX_PASSWORD /fd SHA256 /tr $ts /td SHA256 /d 'ACR Daily' `
          /du 'https://acrdaily.com' $path.Path
        if ($LASTEXITCODE -eq 0) { $ok = $true; break }
      }
      if (-not $ok) { throw "signing $($path.Path) failed" }
      $sig = Get-AuthenticodeSignature $path.Path
      Write-Output "Signed $($path.Path): $($sig.SignerCertificate.Subject) ($($sig.Status))"
    }
  }
} finally {
  Remove-Item $pfx -Force -ErrorAction SilentlyContinue
}

# ACR Daily's code-signing certificate, made once on the maintainer's PC (as https://gist.github.com/PaulCreusy/7fade8d5a8026f2228a97d31343b335e):
# a self-signed certificate for code signing (EKU 1.3.6.1.5.5.7.3.3), valid 5 years, exported as a .pfx with a password,
# and printed in base64 for the GitHub secrets SIGN_PFX_BASE64 and SIGN_PFX_PASSWORD (release.yml: tools/signing/sign.ps1).
#
#   pwsh -File tools\signing\new-certificate.ps1 -Out C:\somewhere\safe
#
# What it gives, honestly: every release then carries a signature (Properties > Digital Signatures: "ACR Daily") and any
# change to the file breaks it. What it doesn't: Windows trusts no self-signed certificate, so SmartScreen's "Windows
# protected your PC" stays until the program has a reputation, and the publisher still reads "Unknown". Only a
# certificate from a trusted authority changes that (an OV certificate, Certum's open-source one, Azure Trusted Signing,
# or SignPath's free plan for open-source projects): sign.ps1 takes any .pfx, so the secret is all that changes then.
param([Parameter(Mandatory = $true)][string]$Out, [string]$Subject = 'CN=ACR Daily, O=ACR Daily, C=GB')
$ErrorActionPreference = 'Stop'
$cert = New-SelfSignedCertificate -Type Custom -Subject $Subject -KeyUsage DigitalSignature -FriendlyName 'ACR Daily code signing' `
  -CertStoreLocation 'Cert:\CurrentUser\My' -KeyExportPolicy Exportable -KeyAlgorithm RSA -KeyLength 3072 `
  -NotAfter (Get-Date).AddYears(5) -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3', '2.5.29.19={text}')
$bytes = New-Object byte[] 24
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$plain = [Convert]::ToBase64String($bytes)
$pw = ConvertTo-SecureString -String $plain -Force -AsPlainText
New-Item -ItemType Directory -Force $Out | Out-Null
$pfx = Join-Path (Resolve-Path $Out) 'acrdaily-codesign.pfx'
Export-PfxCertificate -Cert "Cert:\CurrentUser\My\$($cert.Thumbprint)" -FilePath $pfx -Password $pw | Out-Null
Export-Certificate -Cert "Cert:\CurrentUser\My\$($cert.Thumbprint)" -FilePath (Join-Path (Resolve-Path $Out) 'acrdaily-codesign.cer') | Out-Null
[IO.File]::WriteAllText((Join-Path (Resolve-Path $Out) 'SIGN_PFX_BASE64.txt'), [Convert]::ToBase64String([IO.File]::ReadAllBytes($pfx)))
[IO.File]::WriteAllText((Join-Path (Resolve-Path $Out) 'SIGN_PFX_PASSWORD.txt'), $plain)
Write-Output "Certificate $($cert.Thumbprint) ($Subject), valid to $($cert.NotAfter.ToString('yyyy-MM-dd'))."
Write-Output "In $Out : acrdaily-codesign.pfx, .cer, and the two secrets' values (SIGN_PFX_BASE64.txt, SIGN_PFX_PASSWORD.txt)."
Write-Output 'Add them in GitHub: the repository > Settings > Secrets and variables > Actions; then delete the two .txt files.'

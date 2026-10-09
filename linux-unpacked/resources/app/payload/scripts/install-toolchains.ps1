# install-toolchains.ps1 — install every compiler/gate toolchain VACA uses (Windows).
#
# VACA's non-TS compile gate (backend/src/sandbox/nonTsCompileGate.ts) shells out
# to the real toolchain per language. An unavailable toolchain is a FAILED gate
# ("unverified is never clean"), so a box without these cannot verify a
# Rust/C++/Go/... build. This installs the core desktop/server set:
# C, C++, Rust, Go, Java, C#, Python, PHP, Ruby, Node.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\install-toolchains.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-toolchains.ps1 -Check
#
# Linux/macOS: use scripts/install-toolchains.sh instead.

param([switch]$Check)

function Have($bin) { return [bool](Get-Command $bin -ErrorAction SilentlyContinue) }
function Say($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  OK  $m" -ForegroundColor Green }
function Miss($m) { Write-Host "  --  $m" -ForegroundColor Yellow }

function Report {
  Say "Toolchain status"
  foreach ($bin in @('gcc','g++','clang','rustc','go','javac','dotnet','python','php','ruby','kotlinc','swiftc','node')) {
    if (Have $bin) { Ok "$bin $((& $bin --version 2>&1 | Select-Object -First 1))" }
    else { Miss "$bin MISSING" }
  }
}
Report
if ($Check) { exit 0 }

# Prefer winget; fall back to choco if present.
$Winget = Have 'winget'
$Choco  = Have 'choco'
if (-not $Winget -and -not $Choco) {
  Write-Error "Neither winget nor choco found. Install App Installer (winget) from the Microsoft Store, then re-run."
  exit 1
}

function Install($id, $chocoName) {
  if ($Winget) {
    Say "winget install $id"
    winget install --id $id --accept-source-agreements --accept-package-agreements --silent | Out-Null
  } elseif ($Choco) {
    Say "choco install $chocoName"
    choco install -y $chocoName | Out-Null
  }
}

# C / C++ (MinGW-w64 provides gcc/g++)
if (-not (Have 'gcc') -and -not (Have 'clang')) { Install 'BrechtSanders.WinLibs.POSIX.UCRT' 'mingw' }
# Python
if (-not (Have 'python')) { Install 'Python.Python.3.12' 'python' }
# Java (JDK 17)
if (-not (Have 'javac')) { Install 'Microsoft.OpenJDK.17' 'openjdk17' }
# .NET SDK (C#)
if (-not (Have 'dotnet')) { Install 'Microsoft.DotNet.SDK.8' 'dotnet-sdk' }
# PHP
if (-not (Have 'php')) { Install 'PHP.PHP' 'php' }
# Ruby
if (-not (Have 'ruby')) { Install 'RubyInstallerTeam.Ruby' 'ruby' }
# Go
if (-not (Have 'go')) { Install 'GoLang.Go' 'golang' }
# Rust (rustup)
if (-not (Have 'rustc')) { Install 'Rustlang.Rustup' 'rust' }
# Kotlin (JVM)
if (-not (Have 'kotlinc')) { Install 'JetBrains.Kotlin' 'kotlin' }
# Swift (official toolchain via the Windows Package Manager)
if (-not (Have 'swiftc')) { Install 'Swift.Toolchain' 'swift' }
# Node
if (-not (Have 'node')) { Install 'OpenJS.NodeJS.LTS' 'nodejs-lts' }

Write-Host ""
Say "Done."
Report
Write-Host @"

Open a NEW terminal so PATH changes take effect.
Verify with:  cd backend; npm run toolchains:report
"@ -ForegroundColor Gray

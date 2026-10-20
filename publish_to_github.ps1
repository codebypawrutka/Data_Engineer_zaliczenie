# Publikacja projektu na GitHubie. Uruchom w PowerShellu w J:\olist-pipeline:
#   powershell -ExecutionPolicy Bypass -File .\publish_to_github.ps1 -RepoUrl https://github.com/<login>/olist-pipeline.git
param(
    [Parameter(Mandatory = $true)][string]$RepoUrl
)
Set-Location $PSScriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Brak gita. Zainstaluj: winget install --id Git.Git -e  (potem otwórz nowy PowerShell)" -ForegroundColor Red
    exit 1
}

if (-not (git config --global user.name))  { git config --global user.name  (Read-Host "Imię i nazwisko do commitów") }
if (-not (git config --global user.email)) { git config --global user.email (Read-Host "E-mail do commitów (ten z GitHuba)") }

# J: może nie być dyskiem NTFS - git zgłasza wtedy "dubious ownership"
git config --global --add safe.directory ($PWD.Path -replace '\\', '/')

if (-not (Test-Path .git)) { git init -b main | Out-Null }
git add -A
git status --short

git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "Lokalny potok danych e-commerce Olist: bronze/silver/gold, DQ, model gwiazdy, PySpark, Airflow"
}

$remotes = git remote
if ($remotes -contains "origin") { git remote set-url origin $RepoUrl } else { git remote add origin $RepoUrl }

git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push się nie udał - sprawdź adres repozytorium i logowanie do GitHuba." -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "Gotowe. Link do oddania: $($RepoUrl -replace '\.git$', '')" -ForegroundColor Green

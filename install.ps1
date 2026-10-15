# ============================================================
#  Seagull (海鸥) · opencode 一键部署脚本
#  用法: irm https://raw.githubusercontent.com/ZPTDGIT/seagull-opencode/main/install.ps1 | iex
#  作用: 部署海鸥人格 (AGENTS.md) + 全套技能 -> ~/.config/opencode/
# ============================================================
param(
    [string]$LocalZip = "",
    [string]$SourceDir = "",
    [switch]$NoBackup
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

$Repo    = "ZPTDGIT/seagull-opencode"
$Stamp   = Get-Date -Format "yyyyMMdd-HHmmss"
$Target  = Join-Path $env:USERPROFILE ".config\opencode"
$SkillsT = Join-Path $Target "skills"
$Backup  = Join-Path $Target "_seagull_backup\$Stamp"

function Say([string]$m, [string]$c = "Cyan") { Write-Host $m -ForegroundColor $c }

Say "==================================================" "Green"
Say "  Seagull (海鸥) · opencode 人格+技能 一键部署" "Green"
Say "==================================================" "Green"

# ---------- 1/4 获取部署包 ----------
$work = Join-Path $env:TEMP ("seagull_" + $Stamp)
New-Item -ItemType Directory -Force -Path $work | Out-Null

if ($SourceDir) {
    Say "[1/4] 使用本地目录: $SourceDir"
    $root = (Resolve-Path $SourceDir).Path
} elseif ($LocalZip) {
    Say "[1/4] 解压本地包: $LocalZip"
    Expand-Archive -Path $LocalZip -DestinationPath $work -Force
    $root = (Get-ChildItem $work -Directory | Select-Object -First 1).FullName
} else {
    Say "[1/4] 下载部署包..."
    $urls = @(
        "https://github.com/$Repo/archive/refs/heads/main.zip",
        "https://gh-proxy.com/https://github.com/$Repo/archive/refs/heads/main.zip",
        "https://ghfast.top/https://github.com/$Repo/archive/refs/heads/main.zip"
    )
    $zip = Join-Path $work "pkg.zip"
    $ok = $false
    foreach ($u in $urls) {
        try {
            Say ("      尝试: " + $u) "DarkGray"
            Invoke-WebRequest -Uri $u -OutFile $zip -UseBasicParsing -TimeoutSec 180
            if ((Test-Path $zip) -and (Get-Item $zip).Length -gt 10240) { $ok = $true; break }
        } catch { Say ("      失败: " + $_.Exception.Message) "DarkYellow" }
    }
    if (-not $ok) { throw "所有下载源都失败。请挂代理，或手动下载 zip 后用 -LocalZip 参数安装。" }
    Expand-Archive -Path $zip -DestinationPath $work -Force
    $root = (Get-ChildItem $work -Directory | Where-Object { $_.Name -like "seagull-opencode-*" } | Select-Object -First 1).FullName
    if (-not $root) { $root = (Get-ChildItem $work -Directory | Where-Object { Test-Path (Join-Path $_.FullName "skills") } | Select-Object -First 1).FullName }
    if (-not $root) { throw "解压后找不到包目录。" }
}

$pkgSkills = Join-Path $root "skills"
$pkgAgents = Join-Path $root "AGENTS.md"
if (-not (Test-Path $pkgSkills)) { throw "包不完整：缺少 skills 目录。" }
if (-not (Test-Path $pkgAgents)) { throw "包不完整：缺少 AGENTS.md。" }

# ---------- 2/4 备份 ----------
Say "[2/4] 备份已有配置..."
$nBack = 0
if (-not $NoBackup) {
    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
    $agentsDst = Join-Path $Target "AGENTS.md"
    if (Test-Path $agentsDst) {
        Copy-Item $agentsDst (Join-Path $Backup "AGENTS.md") -Force
        $nBack++
    }
    foreach ($d in Get-ChildItem $pkgSkills -Directory) {
        $ex = Join-Path $SkillsT $d.Name
        if (Test-Path $ex) {
            Copy-Item $ex (Join-Path $Backup ("skills_" + $d.Name)) -Recurse -Force
            $nBack++
        }
    }
    if ($nBack -eq 0) { Remove-Item $Backup -Recurse -Force -ErrorAction SilentlyContinue; Say "      无冲突，无需备份。" }
    else { Say "      已备份 $nBack 项 -> $Backup" }
}

# ---------- 3/4 部署人格 ----------
Say "[3/4] 部署人格 -> $Target\AGENTS.md"
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item $pkgAgents (Join-Path $Target "AGENTS.md") -Force

# ---------- 4/4 部署技能 ----------
Say "[4/4] 部署技能..."
New-Item -ItemType Directory -Force -Path $SkillsT | Out-Null
$n = 0
foreach ($d in Get-ChildItem $pkgSkills -Directory) {
    $dst = Join-Path $SkillsT $d.Name
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Copy-Item $d.FullName $dst -Recurse -Force
    $n++
}
$verify = (Get-ChildItem $SkillsT -Recurse -Filter "SKILL.md" | Measure-Object).Count

Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue

Say ""
Say "==================================================" "Green"
Say "  部署完成: 技能 $n 个，校验到 SKILL.md $verify 个" "Green"
Say "==================================================" "Green"
Say "下一步:" "Yellow"
Say "  1. 重启 opencode（完全退出后再打开）"
Say "  2. 新会话输入「在吗」-> 应回复: 海鸥在线，你要整点薯条吗？"
Say "  3. 输入「逆向」或「渗透」测试技能触发"
if ($nBack -gt 0) { Say "  旧文件已备份到: $Backup" "DarkGray" }

# Initialize planning files for a new session
# Usage: .\init-session.ps1 [-Template TYPE] [project-name]
#        .\init-session.ps1 -Autonomous        # v3 autonomous mode (opt-in)
#        .\init-session.ps1 -Gated             # v3 gated mode (opt-in, implies autonomous)
# Templates: default, analytics
#
# v3 modes (opt-in): -Autonomous / -Gated write a .mode marker next to the plan,
# reset the .stop_blocks gate counter, clear any stale gate ledger, write a fresh
# 16-hex nonce for delimiter framing, and auto-attest the plan. With NO v3 switch
# and no .mode file, behavior is byte-equivalent to v2.43.0.

param(
    [string]$ProjectName = "project",
    [string]$Template = "default",
    [switch]$Autonomous,
    [switch]$Gated
)

$DATE = Get-Date -Format "yyyy-MM-dd"

# Resolve v3 opt-in mode. -Gated implies autonomous and is the stronger marker.
$Mode = ""
if ($Gated) {
    $Mode = "gated"
} elseif ($Autonomous) {
    $Mode = "autonomous"
}

# Resolve template directory (skill root is one level up from scripts/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Split-Path -Parent $ScriptDir
$TemplateDir = Join-Path $SkillRoot "templates"

function Get-Nonce {
    # 16 hex chars for the plan-data delimiter framing (security strand rec 8).
    $bytes = New-Object 'System.Byte[]' 8
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}

Write-Host "Initializing planning files for: $ProjectName (template: $Template)"

# Validate template
if ($Template -ne "default" -and $Template -ne "analytics") {
    Write-Host "Unknown template: $Template (available: default, analytics). Using default."
    $Template = "default"
}

# Create task_plan.md if it doesn't exist
if (-not (Test-Path "task_plan.md")) {
    $AnalyticsPlan = Join-Path $TemplateDir "analytics_task_plan.md"
    if ($Template -eq "analytics" -and (Test-Path $AnalyticsPlan)) {
        Copy-Item $AnalyticsPlan "task_plan.md"
    } else {
        @"
# Task Plan（任务计划）：[简要说明]

## Goal（目标）
[一句话描述最终状态]

## Next Step（下一步）
[下一项具体动作；阶段状态变化时同步更新]

## Current Phase（当前阶段）
Phase 1（阶段 1）

## Phases（阶段）

### Phase 1：需求与调研
- [ ] 理解用户意图
- [ ] 识别约束
- [ ] 记录到 findings.md
- **Status:** in_progress

### Phase 2：规划与结构
- [ ] 确定方案
- [ ] 创建项目结构
- **Status:** pending

### Phase 3：实现
- [ ] 执行计划
- [ ] 执行前先写入文件
- **Status:** pending

### Phase 4：测试与验证
- [ ] 验证需求已满足
- [ ] 记录测试结果
- **Status:** pending

### Phase 5：交付
- [ ] 检查输出
- [ ] 向用户交付
- **Status:** pending

## 已做决策
| 决策 | 理由 |
|------|------|

## 遇到的错误
| 错误 | 解决办法 |
|------|----------|
"@ | Out-File -FilePath "task_plan.md" -Encoding UTF8
    }
    Write-Host "Created task_plan.md"
} else {
    Write-Host "task_plan.md already exists, skipping"
}

# Create findings.md if it doesn't exist
if (-not (Test-Path "findings.md")) {
    $AnalyticsFindings = Join-Path $TemplateDir "analytics_findings.md"
    if ($Template -eq "analytics" -and (Test-Path $AnalyticsFindings)) {
        Copy-Item $AnalyticsFindings "findings.md"
    } else {
        @"
# 发现与决策

## 需求
-

## 调研发现
-

## 技术决策
| 决策 | 理由 |
|------|------|

## 遇到的问题
| 问题 | 解决办法 |
|------|----------|

## 资源
-
"@ | Out-File -FilePath "findings.md" -Encoding UTF8
    }
    Write-Host "Created findings.md"
} else {
    Write-Host "findings.md already exists, skipping"
}

# Create progress.md if it doesn't exist
if (-not (Test-Path "progress.md")) {
    if ($Template -eq "analytics") {
        @"
# 进度日志

## 会话：$DATE

### 当前状态
- **阶段：** 1 - 数据调研
- **开始时间：** $DATE

### 已执行的操作
-

### 查询日志
| 查询 | 结果摘要 | 解读 |
|------|----------|------|

### 错误
| 错误 | 解决办法 |
|------|----------|
"@ | Out-File -FilePath "progress.md" -Encoding UTF8
    } else {
        @"
# 进度日志

## 会话：$DATE

### 当前状态
- **阶段：** 1 - 需求与调研
- **开始时间：** $DATE

### 已执行的操作
-

### 测试结果
| 测试 | 预期 | 实际 | 状态 |
|------|------|------|------|

### 错误
| 错误 | 解决办法 |
|------|----------|
"@ | Out-File -FilePath "progress.md" -Encoding UTF8
    }
    Write-Host "Created progress.md"
} else {
    Write-Host "progress.md already exists, skipping"
}

Write-Host ""
Write-Host "Planning files initialized!"
Write-Host "Files: task_plan.md, findings.md, progress.md"

# v3 opt-in mode side effects. No-op when -Autonomous/-Gated were not passed, so
# the default path stays byte-equivalent to v2.43.0. PS1 init writes in CWD, so
# dotfiles live in CWD and attest-plan.ps1 falls back to the legacy
# .plan-attestation at the project root.
if ($Mode -ne "") {
    $PlanDirPwf = (Get-Location).Path

    # (a) reset gate block counter, drop stale gate ledger.
    Set-Content -LiteralPath (Join-Path $PlanDirPwf ".stop_blocks") -Value "0" -Encoding ascii
    $StaleLedger = Join-Path $PlanDirPwf ".gate_last_ledger"
    if (Test-Path -LiteralPath $StaleLedger) { Remove-Item -LiteralPath $StaleLedger -Force }

    # (b) fresh 16-hex nonce for delimiter framing.
    Set-Content -LiteralPath (Join-Path $PlanDirPwf ".nonce") -Value (Get-Nonce) -NoNewline -Encoding ascii

    # mode marker. gated implies autonomous, so it carries both tokens.
    if ($Mode -eq "gated") {
        $MarkerText = "autonomous gate"
    } else {
        $MarkerText = "autonomous"
    }
    Set-Content -LiteralPath (Join-Path $PlanDirPwf ".mode") -Value $MarkerText -Encoding ascii

    # (c) auto-attest (attestation default-on in v3 modes, security strand rec 1).
    $AttestPs1 = Join-Path $ScriptDir "attest-plan.ps1"
    $PlanFilePwf = Join-Path $PlanDirPwf "task_plan.md"
    if ((Test-Path -LiteralPath $AttestPs1) -and (Test-Path -LiteralPath $PlanFilePwf)) {
        try {
            & $AttestPs1 *> $null
        } catch {
            # attestation failure must not abort init; the mode marker still stands.
        }
    }

    Write-Host "Mode: $MarkerText (attested, gate counter reset)"
}

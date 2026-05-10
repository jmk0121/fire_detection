$ErrorActionPreference = "Stop"

$serviceKey = "6d6f177f3a50b5bbf41528cd764e4db5b684e78fc427885555ffd201e68befe7"
$baseUrl = "http://apis.data.go.kr/1400000/forestStusService/getfirestatsservice"

$projectRoot = Split-Path -Parent $PSScriptRoot
$rawDataDir = Join-Path $projectRoot "data\raw"
$rawOutput = Join-Path $projectRoot "data\raw\forest_fire_incidents.csv"
$nationalOutput = Join-Path $projectRoot "data\processed\forest_fire_daily_national.csv"
$gangneungOutput = Join-Path $projectRoot "data\processed\forest_fire_daily_gangneung.csv"

function Fix-Mojibake([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) {
        return ""
    }

    $latin1 = [System.Text.Encoding]::GetEncoding("ISO-8859-1")
    return [System.Text.Encoding]::UTF8.GetString($latin1.GetBytes($text))
}

function Get-WeatherDates {
    $weatherFile = Get-ChildItem -LiteralPath $rawDataDir -Filter "*.csv" |
        Where-Object { $_.Name -ne "forest_fire_incidents.csv" } |
        Select-Object -First 1
    if (-not $weatherFile) {
        throw "날씨 CSV 파일을 찾지 못했습니다."
    }

    $dates = New-Object System.Collections.Generic.List[string]

    Get-Content -LiteralPath $weatherFile.FullName -Encoding utf8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if (-not [char]::IsDigit($line[0])) { return }

        $parts = $line.Split(",")
        if ($parts.Length -lt 3) { return }

        $dateText = $parts[2].Trim()
        if ($dateText -match '^\d{4}-\d{2}-\d{2}$') {
            $dates.Add($dateText)
        }
    }

    if ($dates.Count -eq 0) {
        throw "날씨 데이터에서 날짜를 찾지 못했습니다."
    }

    return $dates
}

function Get-FirePage([int]$pageNo, [int]$numOfRows, [string]$startDate, [string]$endDate) {
    $params = @{
        ServiceKey = $serviceKey
        pageNo = $pageNo
        numOfRows = $numOfRows
        searchStDt = $startDate.Replace("-", "")
        searchEdDt = $endDate.Replace("-", "")
    }

    $query = ($params.GetEnumerator() | ForEach-Object {
        "{0}={1}" -f $_.Key, [uri]::EscapeDataString([string]$_.Value)
    }) -join "&"

    $uri = "$baseUrl`?$query"
    $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 60
    [xml]$xml = $response.Content

    $resultCode = $xml.response.header.resultCode
    if ($resultCode -ne "00") {
        throw "API 호출 실패: $resultCode $($xml.response.header.resultMsg)"
    }

    $totalCount = [int]$xml.response.body.totalCount
    $items = @()

    foreach ($item in $xml.response.body.items.item) {
        $items += [PSCustomObject]@{
            date = "{0}-{1}-{2}" -f $item.startyear, $item.startmonth, $item.startday
            startyear = [string]$item.startyear
            startmonth = [string]$item.startmonth
            startday = [string]$item.startday
            starttime = [string]$item.starttime
            endyear = [string]$item.endyear
            endmonth = [string]$item.endmonth
            endday = [string]$item.endday
            endtime = [string]$item.endtime
            locsi = Fix-Mojibake ([string]$item.locsi)
            locgungu = Fix-Mojibake ([string]$item.locgungu)
            locmenu = Fix-Mojibake ([string]$item.locmenu)
            locdong = Fix-Mojibake ([string]$item.locdong)
            locbunji = Fix-Mojibake ([string]$item.locbunji)
            firecause = Fix-Mojibake ([string]$item.firecause)
            damagearea = [string]$item.damagearea
        }
    }

    return @{
        totalCount = $totalCount
        items = $items
    }
}

function Is-GangneungIncident($item) {
    $locationText = "$($item.locsi) $($item.locgungu) $($item.locmenu) $($item.locdong)"
    return $locationText.Contains("강릉")
}

function Build-DailyRows($dates, $items, [bool]$onlyGangneung) {
    $map = @{}

    foreach ($item in $items) {
        if ($onlyGangneung -and -not (Is-GangneungIncident $item)) {
            continue
        }

        if (-not $map.ContainsKey($item.date)) {
            $map[$item.date] = @{
                fire_count = 0
                damagearea_total = 0.0
            }
        }

        $map[$item.date].fire_count += 1
        $damage = 0.0
        [void][double]::TryParse($item.damagearea, [ref]$damage)
        $map[$item.date].damagearea_total += $damage
    }

    $rows = @()
    foreach ($date in $dates) {
        $fireCount = 0
        $damageTotal = 0.0

        if ($map.ContainsKey($date)) {
            $fireCount = $map[$date].fire_count
            $damageTotal = $map[$date].damagearea_total
        }

        $rows += [PSCustomObject]@{
            date = $date
            fire_occurred = if ($fireCount -gt 0) { 1 } else { 0 }
            fire_count = $fireCount
            damagearea_total = [math]::Round($damageTotal, 2)
        }
    }

    return $rows
}

$weatherDates = Get-WeatherDates
$startDate = $weatherDates[0]
$endDate = $weatherDates[$weatherDates.Count - 1]

Write-Output "날씨 데이터 기간: $startDate ~ $endDate"

$numOfRows = 500
$firstPage = Get-FirePage -pageNo 1 -numOfRows $numOfRows -startDate $startDate -endDate $endDate
$totalCount = $firstPage.totalCount
$totalPages = [math]::Ceiling($totalCount / $numOfRows)
$allItems = @($firstPage.items)

Write-Output "산불 API 전체 건수: $totalCount"
Write-Output "페이지 수: $totalPages"

for ($pageNo = 2; $pageNo -le $totalPages; $pageNo++) {
    $page = Get-FirePage -pageNo $pageNo -numOfRows $numOfRows -startDate $startDate -endDate $endDate
    $allItems += $page.items
    Write-Output "- $pageNo/$totalPages 페이지 수집 완료"
}

$sortedItems = $allItems | Sort-Object date, starttime
$sortedItems | Export-Csv -LiteralPath $rawOutput -NoTypeInformation -Encoding utf8

$nationalRows = Build-DailyRows -dates $weatherDates -items $sortedItems -onlyGangneung $false
$gangneungRows = Build-DailyRows -dates $weatherDates -items $sortedItems -onlyGangneung $true

$nationalRows | Export-Csv -LiteralPath $nationalOutput -NoTypeInformation -Encoding utf8
$gangneungRows | Export-Csv -LiteralPath $gangneungOutput -NoTypeInformation -Encoding utf8

Write-Output "원본 사건 파일 저장: $rawOutput"
Write-Output "일별 전국 파일 저장: $nationalOutput"
Write-Output "일별 강릉 연계 파일 저장: $gangneungOutput"

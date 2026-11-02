param(
    [Parameter(Mandatory = $true)][string]$DocxPath,
    [int]$SkipParagraphs = -1
)

$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $DocxPath).Path
$word = $null
$document = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($resolved, $false, $true)
    # Edit only the in-memory read-only document; Close(false) never changes the DOCX.
    for ($index = $document.Paragraphs.Count; $index -ge 2; $index--) {
        $paragraph = $document.Paragraphs.Item($index)
        $text = $paragraph.Range.Text.Trim([char]13, [char]7, [char]32)
        if ($text -match '^(Публикация:|ВИЗУАЛ НА ЭКРАН|СХЕМА НА ЭКРАН|КАРТИНКА НА ЭКРАН)' -or $text -eq '— — —') {
            $paragraph.Range.Delete() | Out-Null
        }
    }
    if ($SkipParagraphs -lt 0) { $SkipParagraphs = 1 }
    $start = $document.Content.Start
    for ($number = 1; $number -le $SkipParagraphs; $number++) {
        $start = $document.Paragraphs.Item($number).Range.End
    }
    $body = $document.Range($start, $document.Content.End)
    $body.Copy()
    Start-Sleep -Milliseconds 400
    Write-Output "Copied DOCX body to the rich clipboard: $($body.Characters.Count) characters; skipped $SkipParagraphs opening paragraphs."
}
finally {
    if ($document) { $document.Close($false) | Out-Null }
    if ($word) { $word.Quit() | Out-Null }
}

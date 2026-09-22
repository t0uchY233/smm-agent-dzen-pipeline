param(
    [Parameter(Mandatory = $true)][string]$DocxPath,
    [int]$SkipParagraphs = 2
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

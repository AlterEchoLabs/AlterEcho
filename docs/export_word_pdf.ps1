param([Parameter(Mandatory=$true)][string]$DocumentPath)
$resolvedDocument = (Resolve-Path -LiteralPath $DocumentPath).Path
$pdfPath = [System.IO.Path]::ChangeExtension($resolvedDocument, '.pdf')
$wordApp = New-Object -ComObject Word.Application
$wordApp.Visible = $false
$wordApp.DisplayAlerts = 0
try {
    $document = $wordApp.Documents.Open($resolvedDocument, $false, $true)
    try {
        $document.ExportAsFixedFormat($pdfPath, 17)
    } finally {
        $document.Close(0)
    }
} finally {
    $wordApp.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordApp)
}
Write-Output $pdfPath

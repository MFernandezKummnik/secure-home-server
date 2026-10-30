#Requires -Version 5.1
<#
    backup.ps1 - Woechentliches Offline-Backup vom Server auf die externe Platte "BACKUP"

    Ablauf:
      1. Externe Platte am Namen "BACKUP" erkennen
      2. restic-Passwort aus der verschluesselten Datei laden
      3. Freigaben voruebergehend als Netzlaufwerke Q: bis U: einbinden
      4. Quellen zusammenstellen (Uni-Daten, Musik, Backups-Share, neuestes appdata-Archiv)
      5. Neuen Snapshot erstellen
      6. Alte Snapshots nach Aufbewahrungsregel aufraeumen
      7. Stichprobe der Daten auf der Platte pruefen
      8. Netzlaufwerke trennen und die Platte sicher auswerfen

    Entstanden mit KI-Hilfe (Claude); jede Zeile ist kommentiert und nachvollzogen.
#>

# Bei jedem Fehler in PowerShell-Befehlen sofort abbrechen statt weiterzumachen
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------
$Server        = '\\REYDESERVER'                                  # Servername (backup-Benutzer, nicht die IP)
$Laufwerksname = 'BACKUP'                                         # Volumebezeichnung der externen Platte
$PasswortDatei = Join-Path $PSScriptRoot 'restic-passwort.xml'    # verschluesseltes restic-Passwort

# Freigaben, die waehrend des Backups als Netzlaufwerke eingebunden werden.
# Warum Laufwerke statt \\Server\Freigabe? restic speichert UNC-Pfade unter Windows als
# Ordnernamen mit Backslashes; die lassen sich beim Wiederherstellen nicht anlegen.
# Laufwerksbuchstaben werden dagegen als normale Ordner (/Q, /R, ...) gespeichert.
$Laufwerke = [ordered]@{
    'Q:' = 'Semester1'
    'R:' = 'Semester2'
    'S:' = 'Vorlesungsarchiv'
    'T:' = 'musikRey'
    'U:' = 'Backups'
}

# Platte am Ende automatisch auswerfen ("Hardware sicher entfernen"), damit sie abgesteckt werden kann
$Auswerfen = $true

# Aufbewahrung: die letzten 8 Wochen + je ein Stand pro Monat fuer 12 Monate
$BehalteWochen = 8
$BehalteMonate = 12

# Logdatei mit Datum und Uhrzeit im Namen, im Unterordner "logs" neben dem Skript
$LogOrdner = Join-Path $PSScriptRoot 'logs'
$LogDatei  = Join-Path $LogOrdner ('backup_{0:yyyy-MM-dd_HH-mm}.log' -f (Get-Date))
New-Item -ItemType Directory -Force -Path $LogOrdner | Out-Null

# Alles, was ab hier im Fenster erscheint, zusaetzlich in die Logdatei schreiben
Start-Transcript -Path $LogDatei | Out-Null

# Merkt sich, welche Netzlaufwerke dieser Lauf verbunden hat, damit sie am Ende getrennt werden
$script:Verbunden = @()

# Hilfsfunktion: restic aufrufen und bei einem Fehler abbrechen.
# Externe Programme melden Fehler ueber ihren Exit-Code ($LASTEXITCODE),
# nicht ueber PowerShell-Fehler; deshalb pruefen wir ihn hier selbst.
function Invoke-Restic {
    param([string[]]$Argumente, [int[]]$ErlaubteCodes = @(0))
    & $Restic @Argumente | Out-Host
    if ($ErlaubteCodes -notcontains $LASTEXITCODE) {
        throw "restic $($Argumente[0]) ist mit Exit-Code $LASTEXITCODE fehlgeschlagen."
    }
    return $LASTEXITCODE
}

# Hilfsfunktion: externe Platte so auswerfen wie "Hardware sicher entfernen".
# Windows bietet dafuer kein PowerShell-Cmdlet ohne Adminrechte, aber die
# Systembibliothek cfgmgr32.dll hat genau die Funktion, die Explorer selbst benutzt.
function Invoke-Auswerfen {
    param([string]$Buchstabe)   # z. B. "G"

    # C#-Bruecke zu cfgmgr32.dll nur einmal pro Sitzung laden
    if (-not ('Auswurf' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class Auswurf {
    // Geraete-ID (z. B. "USB\VID_...") -> interne Geraetenummer (DevInst)
    [DllImport("cfgmgr32.dll", CharSet = CharSet.Unicode)]
    static extern int CM_Locate_DevNodeW(out uint devInst, string deviceId, int flags);

    // Geraet sicher entfernen; meldet zurueck, falls Windows es verweigert ("Veto")
    [DllImport("cfgmgr32.dll", CharSet = CharSet.Unicode)]
    static extern int CM_Request_Device_EjectW(uint devInst, out int vetoType,
                                               StringBuilder vetoName, int nameLength, int flags);

    // Gibt null zurueck, wenn es geklappt hat, sonst eine Beschreibung des Problems
    public static string Auswerfen(string deviceId) {
        uint devInst;
        int r = CM_Locate_DevNodeW(out devInst, deviceId, 0);
        if (r != 0) return "Geraet nicht gefunden (Code " + r + ")";

        var vetoName = new StringBuilder(260);
        int vetoType;
        r = CM_Request_Device_EjectW(devInst, out vetoType, vetoName, vetoName.Capacity, 0);
        if (r != 0) return "Auswerfen fehlgeschlagen (Code " + r + ")";
        if (vetoType != 0) return "von Windows verweigert, Grund " + vetoType + ": " + vetoName;
        return null;
    }
}
'@
    }

    # Vom Laufwerksbuchstaben zur physischen Platte: Laufwerk -> Partition -> Festplatte
    $Lw        = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($Buchstabe):'"
    $Partition = Get-CimAssociatedInstance -InputObject $Lw -ResultClassName Win32_DiskPartition
    $Platte    = Get-CimAssociatedInstance -InputObject $Partition -ResultClassName Win32_DiskDrive
    if (-not $Platte) { return "Platte zu $($Buchstabe): nicht gefunden" }

    # Kandidaten: zuerst das uebergeordnete Geraet (der USB-SATA-Adapter), dann die Platte selbst
    $PlattenId = $Platte.PNPDeviceID
    $ElternId  = (Get-PnpDeviceProperty -InstanceId $PlattenId -KeyName 'DEVPKEY_Device_Parent' `
                  -ErrorAction SilentlyContinue).Data

    $Meldung = $null
    foreach ($Id in @($ElternId, $PlattenId)) {
        if (-not $Id) { continue }
        $Meldung = [Auswurf]::Auswerfen($Id)
        if ($null -eq $Meldung) { return $null }   # geklappt
    }
    return $Meldung
}

try {
    # -----------------------------------------------------------------------
    # 0. restic finden: zuerst restic.exe im Skript-Ordner, sonst im Systempfad (PATH)
    # -----------------------------------------------------------------------
    $Restic = Join-Path $PSScriptRoot 'restic.exe'
    if (-not (Test-Path $Restic)) {
        $Gefunden = Get-Command restic -ErrorAction SilentlyContinue
        if (-not $Gefunden) { throw "restic.exe nicht gefunden. Bitte in den Skript-Ordner kopieren." }
        $Restic = $Gefunden.Source
    }
    Write-Host "restic: $Restic"

    # -----------------------------------------------------------------------
    # 1. Externe Platte finden
    # -----------------------------------------------------------------------
    $Volume = Get-Volume -FileSystemLabel $Laufwerksname -ErrorAction SilentlyContinue
    if (-not $Volume -or -not $Volume.DriveLetter) {
        throw "Platte '$Laufwerksname' nicht gefunden. Ist sie angeschlossen und eingeschaltet?"
    }
    $env:RESTIC_REPOSITORY = "$($Volume.DriveLetter):\restic-repo"
    Write-Host "Backup-Ziel: $env:RESTIC_REPOSITORY"

    # -----------------------------------------------------------------------
    # 2. restic-Passwort laden (per Windows-DPAPI verschluesselt)
    # -----------------------------------------------------------------------
    if (-not (Test-Path $PasswortDatei)) {
        throw "Passwortdatei $PasswortDatei fehlt. Siehe Einrichtung in der README."
    }
    $Sicher = Import-Clixml -Path $PasswortDatei
    $env:RESTIC_PASSWORD = [System.Net.NetworkCredential]::new('', $Sicher).Password

    # -----------------------------------------------------------------------
    # 3. Freigaben als Netzlaufwerke einbinden (Anmeldung ueber die per cmdkey
    #    gespeicherten Zugangsdaten des Benutzers "backup")
    # -----------------------------------------------------------------------
    foreach ($Eintrag in $Laufwerke.GetEnumerator()) {
        $Buchstabe = $Eintrag.Key
        $Ziel      = "$Server\$($Eintrag.Value)"

        # Ist der Buchstabe schon belegt? Wenn mit genau dieser Freigabe (Rest eines
        # abgebrochenen Laufs), trennen und neu verbinden. Wenn mit etwas anderem: abbrechen.
        $Belegt = Get-SmbMapping -LocalPath $Buchstabe -ErrorAction SilentlyContinue
        if ($Belegt) {
            if ($Belegt.RemotePath -ne $Ziel) { throw "Laufwerk $Buchstabe ist schon mit $($Belegt.RemotePath) belegt." }
            net use $Buchstabe /delete /y | Out-Null
        }
        elseif (Test-Path "$Buchstabe\") {
            throw "Laufwerk $Buchstabe ist schon belegt (z. B. durch einen USB-Stick)."
        }

        net use $Buchstabe $Ziel /persistent:no | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Konnte $Ziel nicht als $Buchstabe einbinden. Server aus oder Zugangsdaten falsch?" }
        $script:Verbunden += @($Buchstabe)
    }

    # Die vier Datenfreigaben komplett sichern (alle ausser Backups)
    $Quellen = @()
    foreach ($Eintrag in $Laufwerke.GetEnumerator()) {
        if ($Eintrag.Value -ne 'Backups') { $Quellen += "$($Eintrag.Key)\" }
    }

    # -----------------------------------------------------------------------
    # 4. Backups-Freigabe (U:): alles ausser dem appdata-Ordner, davon nur das neueste Archiv
    # -----------------------------------------------------------------------
    # Die Ordner im Backups-Share (z. B. Vaultwarden-Backups) einzeln aufnehmen, ausser "appdata"
    Get-ChildItem 'U:\' | Where-Object { $_.Name -ne 'appdata' } |
        ForEach-Object { $Quellen += $_.FullName }

    # Vom appdata-Plugin nur den neuesten Tagesordner (ab_JJJJMMTT_hhmmss) sichern
    $Neuestes = Get-ChildItem 'U:\appdata' -Directory -Filter 'ab_*' |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $Neuestes) { throw "Kein appdata-Backup (ab_*) im Backups-Share gefunden." }
    $Quellen += $Neuestes.FullName

    Write-Host "`nGesichert werden:"
    $Quellen | ForEach-Object { Write-Host "  $_" }

    # -----------------------------------------------------------------------
    # 5. Snapshot erstellen
    # -----------------------------------------------------------------------
    # Exit-Code 3 = Snapshot erstellt, aber einzelne Dateien waren nicht lesbar -> Warnung, kein Abbruch
    Write-Host "`n=== Backup ==="
    # --group-by host,tags: den Vorgaenger-Snapshot ("Parent") nach Rechner und Tag suchen statt nach
    # den Pfaden. Der appdata-Ordner heisst jeden Tag anders, nach Pfaden gaebe es nie einen Parent,
    # und restic muesste jedes Mal alle Dateien neu lesen statt unveraenderte zu ueberspringen.
    $Code = Invoke-Restic -Argumente (@('backup', '--tag', 'woechentlich', '--group-by', 'host,tags') + $Quellen) -ErlaubteCodes @(0, 3)
    if ($Code -eq 3) { Write-Warning 'Einige Dateien konnten nicht gelesen werden. Details stehen oben im Log.' }

    # -----------------------------------------------------------------------
    # 6. Alte Snapshots aufraeumen
    # -----------------------------------------------------------------------
    # --group-by host: alle Snapshots dieses PCs gemeinsam bewerten. Ohne das wuerde restic
    # nach Pfaden gruppieren, und weil der appdata-Ordner jede Woche anders heisst,
    # waere jeder Snapshot seine eigene Gruppe und wuerde nie geloescht.
    Write-Host "`n=== Aufraeumen ==="
    Invoke-Restic -Argumente @('forget', '--group-by', 'host',
        '--keep-weekly', $BehalteWochen, '--keep-monthly', $BehalteMonate, '--prune') | Out-Null

    # -----------------------------------------------------------------------
    # 7. Stichprobe pruefen: 5 % der gespeicherten Daten wirklich lesen und kontrollieren
    # -----------------------------------------------------------------------
    Write-Host "`n=== Pruefung ==="
    Invoke-Restic -Argumente @('check', '--read-data-subset=5%') | Out-Null

    Write-Host "`nBackup erfolgreich abgeschlossen." -ForegroundColor Green
}
catch {
    Write-Host "`nFEHLER: $($_.Exception.Message)" -ForegroundColor Red
    $global:Fehlgeschlagen = $true
}
finally {
    # Eingebundene Netzlaufwerke wieder trennen (auch wenn vorher ein Fehler auftrat)
    foreach ($Buchstabe in $script:Verbunden) { net use $Buchstabe /delete /y | Out-Null }

    # Passwort und Repository wieder aus den Umgebungsvariablen entfernen
    Remove-Item Env:RESTIC_PASSWORD   -ErrorAction SilentlyContinue
    Remove-Item Env:RESTIC_REPOSITORY -ErrorAction SilentlyContinue

    # Platte sicher auswerfen (auch nach einem Fehler, solange sie gefunden wurde).
    # Ein Problem dabei laesst das Backup NICHT als fehlgeschlagen gelten.
    if ($Auswerfen -and $Volume -and $Volume.DriveLetter) {
        try {
            $Problem = Invoke-Auswerfen -Buchstabe $Volume.DriveLetter
            if ($null -eq $Problem) {
                Write-Host "Platte ausgeworfen. Du kannst sie jetzt ausschalten und abstecken." -ForegroundColor Green
            } else {
                Write-Warning "Platte konnte nicht ausgeworfen werden: $Problem"
                Write-Warning "Bitte ueber 'Hardware sicher entfernen' auswerfen, bevor du sie absteckst."
            }
        } catch {
            Write-Warning "Platte konnte nicht ausgeworfen werden: $($_.Exception.Message)"
        }
    }
    Stop-Transcript | Out-Null
    Write-Host "Log: $LogDatei"
}

if ($global:Fehlgeschlagen) { exit 1 }

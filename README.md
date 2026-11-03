# PyPack

**PyPack** ist ein verlustfreies, adaptives Archivierungsprogramm für Windows. Es erstellt Archive aus einzelnen Dateien und ganzen Ordnern und kann deren Inhalt wiederherstellen und überprüfen.

> **Closed Source:** Der Programmcode von PyPack wird nicht veröffentlicht. Dieses Repository dient ausschließlich zur Bereitstellung offizieller Downloads und Informationen zu Updates.

## Download

[**PyPack-Setup.exe herunterladen**](https://github.com/MadMax20108/PyPack/raw/refs/heads/main/PyPack-Setup.exe)

Der Download startet den Windows-Installer. Installiere PyPack ausschließlich aus diesem offiziellen Repository.

- **Plattform:** Windows
- **Paket:** Windows-Setup (EXE)
- **Installation:** über den mitgelieferten Installer

## Funktionen

- Verlustfreie Archivierung von Dateien und Ordnern
- Adaptive Auswahl geeigneter Kompressionsverfahren
- Eigene RLE-Strategie für Daten mit langen Wiederholungen gleicher Bytes
- Mehrere Worker für parallele Verarbeitung
- SHA-256-Prüfsummen zur Erkennung beschädigter Archive
- Archive auflisten, überprüfen und vollständig oder teilweise entpacken
- Grafische Oberfläche und Kommandozeilenbedienung
- .pyp-Dateizuordnung unter Windows

Die tatsächliche Kompressionsrate hängt von den Eingabedaten ab. Bereits komprimierte Formate wie JPEG oder MP4 werden normalerweise kaum weiter verkleinert.

## Updates

Dieses Repository ist die offizielle Quelle für PyPack-Downloads.

Sobald eine neue Version veröffentlicht wird, wird der Download hier aktualisiert. Für eine manuelle Aktualisierung kannst du den Installer von dieser Seite erneut herunterladen und ausführen.

**Hinweis zum automatischen Updater:** Die Bereitstellung eines Downloads allein implementiert noch keine Updateprüfung in der installierten Anwendung. Dafür muss PyPack selbst eine Versionsabfrage durchführen. Derzeit ist in diesem Repository kein öffentlich dokumentierter Update-Endpunkt und kein Release-Verlauf hinterlegt.

## Hinweise

- PyPack erstellt verlustfreie Archive; Dateien sollen nach dem Entpacken bytegenau wiederhergestellt werden.
- Das Archivformat ist derzeit noch nicht als langfristig stabiles Format spezifiziert.
- Bewahre wichtige Originaldateien zusätzlich auf und prüfe Archive nach dem Erstellen.

## Lizenz und Nutzung

PyPack ist proprietäre, nicht frei lizenzierte Software. Es wird keine Lizenz zur Weiterverwendung, Änderung oder Weiterverbreitung des Programms oder seines Codes erteilt. Alle Rechte bleiben vorbehalten.

Details stehen in [PROPRIETARY-NOTICE.txt](PROPRIETARY-NOTICE.txt).

## Support und Fehlerberichte

Wenn du einen Fehler melden oder eine Frage stellen möchtest, kannst du dafür die [GitHub-Issues](https://github.com/MadMax20108/PyPack/issues) verwenden. Bitte veröffentliche dort keine privaten Dateien oder vertraulichen Informationen.

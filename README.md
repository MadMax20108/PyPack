# PyPack

**PyPack** ist ein verlustfreies, adaptives Archivierungsprogramm für Windows. Es erstellt Archive aus einzelnen Dateien und ganzen Ordnern und kann deren Inhalt wiederherstellen und überprüfen.

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

Die Datei [latest.json](latest.json) enthält die aktuelle Versionsnummer, den Download-Link und die Versionshinweise. Für eine manuelle Aktualisierung kannst du den Installer von dieser Seite erneut herunterladen und ausführen.

## Lizenz und Nutzung

PyPack ist proprietäre, nicht frei lizenzierte Software. Es wird keine Lizenz zur Weiterverwendung, Änderung oder Weiterverbreitung des Programms oder seines Codes erteilt. Alle Rechte bleiben vorbehalten.

Details stehen in [PROPRIETARY-NOTICE.txt](PROPRIETARY-NOTICE.txt).

## Support und Fehlerberichte

Wenn du einen Fehler melden oder eine Frage stellen möchtest, kannst du dafür die [GitHub-Issues](https://github.com/MadMax20108/PyPack/issues) verwenden. Bitte veröffentliche dort keine privaten Dateien oder vertraulichen Informationen.

---

# PyPack (English)

**PyPack** is a lossless, adaptive archiving application for Windows. It creates archives from individual files and entire folders, and can restore and verify their contents.

## Download

[**Download PyPack-Setup.exe**](https://github.com/MadMax20108/PyPack/raw/refs/heads/main/PyPack-Setup.exe)

The download starts the Windows installer. Only install PyPack from this official repository.

- **Platform:** Windows
- **Package:** Windows installer (EXE)
- **Installation:** Using the included installer

## Features

- Lossless archiving of files and folders
- Adaptive selection of suitable compression methods
- Custom RLE strategy for data containing long runs of repeated bytes
- Multiple workers for parallel processing
- SHA-256 checksums to detect corrupted archives
- List and verify archives, and extract them fully or partially
- Graphical user interface and command-line support
- .pyp file association on Windows

The actual compression ratio depends on the input data. Already compressed formats such as JPEG or MP4 usually cannot be reduced much further.

## Updates

This repository is the official source for PyPack downloads.

The [latest.json](latest.json) file contains the current version number, download link, and release notes. To update manually, download the installer from this page again and run it.

## License and Usage

PyPack is proprietary software and is not distributed under an open-source license. No license is granted to reuse, modify, or redistribute the program or its source code. All rights are reserved.

See [PROPRIETARY-NOTICE.txt](PROPRIETARY-NOTICE.txt) for details.

## Support and Bug Reports

If you want to report a bug or ask a question, you can use [GitHub Issues](https://github.com/MadMax20108/PyPack/issues). Please do not publish private files or confidential information there.

# PyPack — verlustfreies, adaptives Archiv

PyPack ist ein Python-MVP für verlustfreie Datei- und Ordnerarchive. Pro Datei wird einmal anhand einer Stichprobe der passende Codec bzw. die RLE-Strategie ausgewählt; danach komprimieren parallele Worker alle Blöcke dieser Datei mit derselben Strategie und schreiben sie geordnet ins Archiv. SHA-256-Prüfsummen erkennen beschädigte Archive.

> Die eigene RLE-Technik ist besonders für lange Wiederholungen gleicher Bytes gedacht. Sie wird nur genutzt, wenn sie tatsächlich kleiner als die Rohdaten ist; die adaptive Auswahl vergleicht zusätzlich etablierte Codecs. Das ist kein Versprechen, ZIP für jede Eingabe zu schlagen. Bereits komprimierte Formate wie JPEG und MP4 werden normalerweise unverändert gespeichert. Dateien werden beim Entpacken bytegenau rekonstruiert.

## Voraussetzungen

- Python 3.10 oder neuer
- GUI: `python -m pip install -r requirements.txt`
- CLI und Archivkern benötigen keine externen Abhängigkeiten
- Optionale CUDA-RLE-Analyse: eine passende CUDA-fähige PyTorch-Installation und kompatible NVIDIA-Treiber; wird zur Laufzeit geprüft

## Eigener Windows-Installer und .pyp-Dateizuordnung

Führe `build_windows.bat` aus, um eine kompakte `dist/PyPack.exe` samt Icon zu bauen. Der Build schließt große, nicht benötigte ML-/GPU-Pakete aus (PyTorch, Transformers, NumPy, SciPy usw.); dadurch enthält die portable Standard-EXE keine CUDA-Laufzeit. Kompiliere anschließend `installer/PyPack.iss` mit Inno Setup. Der Inno-Installer richtet die `.pyp`-Dateizuordnung und Verknüpfungen ein. Das eigenständige Python-Setup wurde entfernt; der Inno-Installer ist der einzige unterstützte Installationsweg.

Der Build schließt CUDA/PyTorch bewusst aus, damit der Windows-Installer nicht unnötig mehrere Gigabyte groß wird; die optionale GPU-Beschleunigung erfordert eine separate passende Python/CUDA-Installation.

## Grafische Oberfläche

```console
python -m pip install -r requirements.txt
python gui.py
```

Die GUI kann Archive aus einzelnen Dateien und/oder ganzen Ordnern erstellen, Archive öffnen, den Inhalt als Dateibaum ansehen, Dateien auswählen und einzeln in einen Zielordner kopieren/entpacken, alles entpacken und Archive prüfen. Beim Erstellen lässt sich die Kompressionsstärke von 1 (schnell) bis 9 (stärker, meist langsamer) einstellen; die zuletzt gewählte Stufe wird gemerkt. Während der Arbeit zeigt die Statusleiste die aktuelle Workerzahl. Entpacken und Prüfen reichen mehrere Blöcke in Batches ein, um den Worker-Pool besser auszulasten; Ergebnisse werden in Archiv-Reihenfolge verarbeitet. Der Abbrechen-Button neben dem Fortschrittsbalken stoppt Packen, Entpacken oder Prüfen und entfernt unvollständige temporäre Dateien. Im Einstellungsbereich kann der integrierte Dateibaum-Auswahldialog ein- oder ausgeschaltet werden; ausgeschaltet stehen separate Dialoge für Datei- und Ordnerauswahl bereit.

## Verwendung

```console
python pypack.py pack ordner -o backup.pyp
python pypack.py list backup.pyp
python pypack.py test backup.pyp
python pypack.py unpack backup.pyp -o wiederhergestellt
```

Einzelne Dateien und mehrere Eingaben sind ebenfalls möglich. `--level 1` bis `--level 9` steuert die Kompressionsstärke; `--mode fast` (Standard) wählt den Codec einmal anhand einer Dateistichprobe; `--mode maximum` vergleicht pro Block Store, zlib, bz2, lzma und die eigene RLE+zlib-Variante und speichert den kleinsten Kandidaten. Das braucht deutlich mehr Rechenzeit und garantiert nicht das global kleinstmögliche Archiv, prüft aber jede derzeit unterstützte Variante für jeden Block. Die GUI bietet dieselbe Auswahl unter „Kompression“. `--workers auto` startet mit mehreren Thread-Workern und regelt die Zahl anhand der CPU-Auslastung. Threads vermeiden zusätzliche GUI-Prozesse in der gebündelten Windows-EXE; die nativen Kompressionscodecs können parallel laufen. GPU-Hardware wird automatisch erkannt und nur bei erfolgreichem CUDA-Test mitverwendet; `--cpu-only` erzwingt CPU-Betrieb. Eine feste Workerzahl lässt sich mit `--workers N` vorgeben. Die GUI führt den Packvorgang selbst in einem Hintergrundthread aus und zeigt Fortschritt sowie Restzeit. Ohne `-o` erstellt PyPack automatisch einen passenden, kollisionsfreien Archivnamen neben der Eingabe.

## Format und Sicherheitsmerkmale

Das Format ist versioniert und blockorientiert. Jeder Block enthält Pfad, Größe, Codec (einschließlich PyPack-RLE), Prüfsumme und Datenlängen. Der Leser begrenzt Metadaten und Blockgrößen, lehnt Pfadtraversierung, doppelte Pfade und symbolische Links ab und prüft Prüfsummen vor dem Schreiben. Extraktion überschreibt standardmäßig keine vorhandenen Dateien; `--overwrite` erlaubt das ausdrücklich.

Dieses erste Format ist noch nicht als langfristig stabil spezifiziert. Vor produktiver Nutzung sollten Formatversionierung, Fuzzing und unabhängige Sicherheitsreviews ergänzt werden.

## Tests

```console
python -m unittest discover -s tests -v
```

"""PyPack: kleines, sicheres und adaptives verlustfreies Archivformat."""

from __future__ import annotations

import argparse
import bz2
import concurrent.futures
import multiprocessing
import hashlib
import lzma
import os
from collections import deque
from pathlib import Path, PurePosixPath
import struct
import sys
import time
import zlib

MAGIC = b"PYPACK\x00\x01"
VERSION = 1
BLOCK_SIZE = 1024 * 1024
MAX_NAME = 16 * 1024
MAX_META = 64 * 1024
MAX_BLOCK = 64 * 1024 * 1024
MAX_ENTRIES = 1_000_000
MAX_WORKERS = min(64, max(4, (os.cpu_count() or 1) * 2))
CPU_TARGET_PERCENT = 80.0
CPU_HIGH_SAMPLES_BEFORE_SCALE_DOWN = 4
CPU_LOW_SAMPLES_BEFORE_SCALE_UP = 2
# Codec 4 ist PyPack RLE: eine eigene, vollständig umkehrbare Byte-Run-Length-
# Transformation. Sie hilft bei Daten mit langen identischen Bytefolgen.
CODECS = {0: "store", 1: "zlib", 2: "bz2", 3: "lzma", 4: "pypack-rle+zlib"}
CODEC_IDS = {name: ident for ident, name in CODECS.items()}


class ArchiveError(Exception):
    """Ungültiges oder beschädigtes Archiv."""


class AdaptiveWorkers:
    """Passt Parallelität anhand der CPU-Auslastung an (psutil optional)."""

    def __init__(self, initial: int | None = None, maximum: int = MAX_WORKERS,
                 target_percent: float = CPU_TARGET_PERCENT):
        self.maximum = max(1, min(maximum, MAX_WORKERS))
        self.target_percent = target_percent
        # Start mit mehreren Arbeitern, damit ein großes Archiv gleich parallel
        # beginnt; anschließende Messungen regeln anhand der Systemlast nach.
        self.current = max(1, min(initial or min(max(4, (os.cpu_count() or 1) * 2), self.maximum), self.maximum))
        self._psutil = None
        self._high_samples = 0
        self._low_samples = 0
        try:
            import psutil
            self._psutil = psutil
            psutil.cpu_percent(interval=None)
        except ImportError:
            pass
        self.last_check = time.monotonic()

    @property
    def available(self) -> bool:
        return self._psutil is not None

    def sample(self) -> int:
        """CPU-Auslastung abfragen und höchstens einmal pro Sekunde nachregeln."""
        if self._psutil is None or time.monotonic() - self.last_check < 1.0:
            return self.current
        self.last_check = time.monotonic()
        usage = float(self._psutil.cpu_percent(interval=None))
        if usage >= self.target_percent + 5:
            self._high_samples += 1
            self._low_samples = 0
        elif usage <= self.target_percent - 15:
            self._low_samples += 1
            self._high_samples = 0
        else:
            self._high_samples = 0
            self._low_samples = 0

        # Hysterese + mehrere bestätigte Messungen: kurze CPU-Spitzen lösen
        # kein sofortiges Verkleinern des Pools aus.
        if self._high_samples >= CPU_HIGH_SAMPLES_BEFORE_SCALE_DOWN:
            self.current = max(1, self.current - max(1, self.current // 4))
            self._high_samples = 0
        elif self._low_samples >= CPU_LOW_SAMPLES_BEFORE_SCALE_UP:
            self.current = min(self.maximum, self.current + max(1, self.current // 4))
            self._low_samples = 0
        return self.current


def _validate_workers(workers: int | str) -> int | None:
    if workers == "auto":
        return None
    count = int(workers)
    if count < 1 or count > MAX_WORKERS:
        raise ValueError(f"Workerzahl muss zwischen 1 und {MAX_WORKERS} liegen")
    return count


def _compress(data: bytes, level: int) -> tuple[int, bytes]:
    """Fast-path ordering preserves the previous best-size selection.

    zlib is the quick baseline. RLE only runs for blocks with repeated-byte
    evidence; bz2/lzma are skipped only when the best result so far is not
    smaller than store (store is then guaranteed to win or tie).
    """
    best = (0, data)
    zlib_payload = zlib.compress(data, level)
    if len(zlib_payload) < len(best[1]):
        best = (1, zlib_payload)

    # Evaluate all supported lossless candidates even when they expand data;
    # store remains a candidate and wins unless a codec is actually smaller.
    bz_payload = bz2.compress(data, compresslevel=min(9, max(1, level)))
    if len(bz_payload) < len(best[1]):
        best = (2, bz_payload)
    lz_payload = lzma.compress(data, preset=min(9, max(0, level - 1)))
    if len(lz_payload) < len(best[1]):
        best = (3, lz_payload)

    # Custom reversible RLE + zlib is another codec candidate for every block.
    rle_payload = zlib.compress(_rle_encode(data), level)
    if len(rle_payload) < len(best[1]):
        best = (4, rle_payload)
    return best


def _rle_encode(data: bytes) -> bytes:
    """PackBits-artige reversible RLE-Codierung mit maximal 128 Byte pro Run."""
    out = bytearray()
    i = 0
    while i < len(data):
        run = 1
        while i + run < len(data) and data[i + run] == data[i] and run < 128:
            run += 1
        if run >= 4:
            out.extend((0x80 | (run - 1), data[i]))
            i += run
            continue
        start = i
        i += run
        while i < len(data) and i - start < 128:
            next_run = 1
            while i + next_run < len(data) and data[i + next_run] == data[i] and next_run < 128:
                next_run += 1
            if next_run >= 4:
                break
            i += min(next_run, 128 - (i - start))
        literal = data[start:i]
        out.append(len(literal) - 1)
        out.extend(literal)
    return bytes(out)


def _rle_decode(data: bytes, expected_size: int) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        control = data[i]
        i += 1
        count = (control & 0x7F) + 1
        if control & 0x80:
            if i >= len(data):
                raise ArchiveError("Abgeschnittener RLE-Lauf")
            out.extend(bytes((data[i],)) * count)
            i += 1
        else:
            if i + count > len(data):
                raise ArchiveError("Abgeschnittener RLE-Literalblock")
            out.extend(data[i:i + count])
            i += count
        if len(out) > expected_size:
            raise ArchiveError("RLE-Ausgabe überschreitet Blockgröße")
    if len(out) != expected_size:
        raise ArchiveError("RLE-Ausgabe hat falsche Blockgröße")
    return bytes(out)


def _decompress(codec: int, payload: bytes, expected_size: int | None = None) -> bytes:
    try:
        if codec == 0:
            return payload
        if codec == 1:
            return zlib.decompress(payload)
        if codec == 2:
            return bz2.decompress(payload)
        if codec == 3:
            return lzma.decompress(payload)
        if codec == 4:
            if expected_size is None:
                raise ArchiveError("RLE-Block ohne Zielgröße")
            return _rle_decode(zlib.decompress(payload), expected_size)
    except (OSError, EOFError, lzma.LZMAError, zlib.error) as exc:
        raise ArchiveError(f"Block konnte nicht dekomprimiert werden: {exc}") from exc
    raise ArchiveError(f"Unbekannter Codec: {codec}")


def _inputs(paths: list[Path]) -> list[tuple[Path, str]]:
    """Erzeuge eindeutige, relative Archivpfade für Dateien und Ordner."""
    result: list[tuple[Path, str]] = []
    names: set[str] = set()
    for source in paths:
        source = source.resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        if source.is_symlink():
            raise ValueError(f"Symbolische Links werden nicht archiviert: {source}")
        if source.is_file():
            entries = [(source, source.name)]
        elif source.is_dir():
            entries = []
            for file in sorted(source.rglob("*")):
                if file.is_symlink():
                    raise ValueError(f"Symbolischer Link im Eingabeordner: {file}")
                if file.is_file():
                    entries.append((file, (Path(source.name) / file.relative_to(source)).as_posix()))
        else:
            raise ValueError(f"Nicht unterstützter Eingabetyp: {source}")
        for file, name in entries:
            if name in names:
                raise ValueError(f"Doppelter Archivpfad: {name}")
            names.add(name)
            result.append((file, name))
    return result


def default_archive_name(paths: list[Path]) -> Path:
    """Erzeuge automatisch einen eindeutigen Archivnamen neben der Eingabe."""
    resolved = [Path(path).resolve() for path in paths]
    if len(resolved) == 1:
        source = resolved[0]
        base = source.name if source.is_dir() else source.stem
        parent = source.parent
    else:
        base = resolved[0].parent.name or "PyPack"
        parent = resolved[0].parent
        if not base:
            base = "PyPack-Archiv"
        base += f"_und_{len(resolved) - 1}_weitere"
    candidate = parent / f"{base}.pyp"
    index = 2
    while candidate.exists():
        candidate = parent / f"{base}_{index}.pyp"
        index += 1
    return candidate


def _encode_block(data: bytes, level: int) -> tuple[int, bytes, bytes]:
    codec, payload = _compress(data, level)
    return codec, payload, hashlib.sha256(data).digest()


def _choose_file_strategy(sample: bytes, level: int, use_gpu: bool = False) -> tuple[int, bool]:
    """Pick one encoding strategy from a file sample, once per input file."""
    candidates: list[tuple[int, int]] = [(0, len(sample))]
    z_payload = zlib.compress(sample, level)
    candidates.append((1, len(z_payload)))
    candidates.append((2, len(bz2.compress(sample, compresslevel=min(9, max(1, level))))))
    candidates.append((3, len(lzma.compress(sample, preset=min(9, max(0, level - 1))))))
    rle_enabled = False
    transformed = _rle_encode(sample)
    if len(transformed) < len(sample):
        rle_size = len(zlib.compress(transformed, level))
        candidates.append((4, rle_size))
        rle_enabled = rle_size < min(length for codec, length in candidates if codec != 4)
    chosen_codec, _ = min(candidates, key=lambda candidate: candidate[1])
    return chosen_codec, chosen_codec == 4 or rle_enabled


def _max_compress_worker(data: bytes, level: int, use_gpu: bool = False):
    """Exhaustively compare store, zlib, bz2, lzma and custom RLE per block."""
    if use_gpu:
        # GPU is a candidate accelerator; exact CPU candidates still decide size.
        gpu_result = _gpu_rle_candidate(data, level)
    else:
        gpu_result = None
    candidates = [(0, data), (1, zlib.compress(data, level)),
                  (2, bz2.compress(data, compresslevel=min(9, max(1, level)))),
                  (3, lzma.compress(data, preset=min(9, max(0, level - 1)))),
                  (4, zlib.compress(_rle_encode(data), level))]
    codec, payload = min(candidates, key=lambda candidate: len(candidate[1]))
    digest = hashlib.sha256(data).digest()
    if gpu_result is not None and len(gpu_result[1]) < len(payload):
        return gpu_result
    return codec, payload, digest


def _encode_with_strategy(data: bytes, strategy: tuple[int, bool], level: int) -> tuple[int, bytes, bytes]:
    codec, use_rle = strategy
    if codec == 0:
        payload = data
    elif codec == 1:
        payload = zlib.compress(data, level)
    elif codec == 2:
        payload = bz2.compress(data, compresslevel=min(9, max(1, level)))
    elif codec == 3:
        payload = lzma.compress(data, preset=min(9, max(0, level - 1)))
    elif codec == 4 or use_rle:
        transformed = _rle_encode(data)
        payload = zlib.compress(transformed, level)
        codec = 4
    else:
        payload = data
        codec = 0
    return codec, payload, hashlib.sha256(data).digest()


def _encode_strategy_worker(data: bytes, strategy: tuple[int, bool], level: int):
    return _encode_with_strategy(data, strategy, level)


def _encode_block_worker(data: bytes, level: int, use_gpu: bool = False) -> tuple[int, bytes, bytes]:
    """Pickle-friendly module-level worker for CPU-parallel compression."""
    if use_gpu:
        gpu_result = _gpu_rle_candidate(data, level)
        if gpu_result is not None:
            standard = _encode_block(data, level)
            if len(gpu_result[1]) < len(standard[1]):
                return gpu_result
            return standard
    # Common low-latency policy: try zlib first; for very compressible blocks,
    # compare slower codecs only if they can produce a worthwhile size gain.
    zlib_payload = zlib.compress(data, level)
    if len(zlib_payload) >= len(data):
        return 0, data, hashlib.sha256(data).digest()
    best = (1, zlib_payload)
    # BZ2 is relatively fast and can beat zlib on text-like data.
    bz_payload = bz2.compress(data, compresslevel=min(9, max(1, level)))
    if len(bz_payload) < len(best[1]):
        best = (2, bz_payload)
    # Keep LZMA in the candidate sweep to preserve the previous best-size
    # behavior. Its native implementation releases the GIL and runs in workers.
    lz_payload = lzma.compress(data, preset=min(9, max(0, level - 1)))
    if len(lz_payload) < len(best[1]):
        best = (3, lz_payload)
    return best[0], best[1], hashlib.sha256(data).digest()


def _gpu_rle_candidate(data: bytes, level: int) -> tuple[int, bytes, bytes] | None:
    """Try the custom RLE prepass on CUDA; returns None if CUDA is unavailable.

    GPU handles the byte-run detection while Python performs the final stream
    assembly and zlib coding. This is an optional accelerator, not a CUDA codec.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        # Transfer a block to the selected CUDA device and compute run starts.
        values = torch.frombuffer(bytearray(data), dtype=torch.uint8).to("cuda")
        if values.numel() < 2:
            return None
        starts = torch.empty_like(values, dtype=torch.bool)
        starts[0] = True
        starts[1:] = values[1:] != values[:-1]
        positions = torch.nonzero(starts).flatten().cpu().tolist()
        # RLE encoding itself needs literal/run tokenization; reuse the proven
        # CPU encoder when the GPU detects a useful repeated-byte block.
        run_count = len(positions)
        if run_count > len(data) * 0.75:
            return None
        transformed = _rle_encode(data)
        if len(transformed) >= len(data):
            return None
        packed = zlib.compress(transformed, level)
        if len(packed) >= len(zlib.compress(data, level)):
            return None
        return 4, packed, hashlib.sha256(data).digest()
    except (ImportError, RuntimeError, OSError, TypeError):
        return None


def gpu_available() -> bool:
    """Detect a CUDA GPU by running a tiny real operation on it (optional torch)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        return int(torch.ones(1, device="cuda").item()) == 1
    except (ImportError, RuntimeError, OSError, AssertionError):
        return False


def gpu_available_lightweight() -> bool:
    """Use torch CUDA only when already installed; do not require it for CPU builds."""
    return gpu_available()


def pack(paths: list[Path], output: Path, level: int = 6, workers: int | str = "auto",
         progress_callback=None, use_gpu: bool | None = None, mode: str = "fast",
         cancel_event=None) -> None:
    if mode not in {"fast", "maximum"}:
        raise ValueError("mode muss 'fast' oder 'maximum' sein")
    entries = _inputs(paths)
    if len(entries) > MAX_ENTRIES:
        raise ValueError("Zu viele Dateien")
    output = output.resolve()
    for file, _ in entries:
        if file == output:
            raise ValueError("Ausgabearchiv darf keine Eingabedatei überschreiben")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Schreibe zunächst in eine temporäre Datei, damit Fehler kein halbes Archiv hinterlassen.
    temp = output.with_name(output.name + ".tmp")
    try:
        total_bytes = sum(file.stat().st_size for file, _ in entries)
        processed_bytes = 0
        start_time = time.monotonic()

        def report_progress(current_name: str = ""):
            if progress_callback is None:
                return
            elapsed = max(0.001, time.monotonic() - start_time)
            rate = processed_bytes / elapsed
            remaining = max(0, total_bytes - processed_bytes)
            eta = remaining / rate if rate > 0 else None
            worker_count = current_pool_size if "current_pool_size" in locals() else 1
            progress_callback(processed_bytes, total_bytes, eta, current_name, worker_count)

        with temp.open("wb") as archive:
            archive.write(MAGIC)
            archive.write(struct.pack(">I", len(entries)))
            fixed_workers = None if workers == "auto" else int(workers)
            adaptive = AdaptiveWorkers(initial=fixed_workers)
            # PyTorch/CUDA is intentionally not imported or bundled in the
            # default compact Windows build; use CPU unless a future lightweight
            # CUDA backend is installed explicitly.
            gpu_enabled = False if use_gpu is None else bool(use_gpu and gpu_available_lightweight())
            current_pool_size = 0
            pool = None
            pending: deque[tuple[int, concurrent.futures.Future]] = deque()
            try:
                for file, name in entries:
                    _check_cancel(cancel_event)
                    report_progress(name)
                    encoded = name.encode("utf-8")
                    if len(encoded) > MAX_NAME:
                        raise ValueError(f"Pfadname zu lang: {name}")
                    size = file.stat().st_size
                    archive.write(struct.pack(">HQ", len(encoded), size))
                    archive.write(encoded)
                    # Die aufwändige Codec-Auswahl läuft genau einmal je Datei,
                    # anhand einer Stichprobe. Alle Datenblöcke nutzen danach
                    # denselben Codec (bzw. dieselbe RLE-Strategie).
                    strategy = None
                    if mode == "fast":
                        with file.open("rb") as sample_stream:
                            sample = sample_stream.read(min(size, 256 * 1024))
                        strategy = _choose_file_strategy(sample, level, gpu_enabled)
                    with file.open("rb") as stream:
                        while True:
                            _check_cancel(cancel_event)
                            # Auf CPU-Last reagieren und den Threadpool bei Bedarf
                            # kontrolliert auf eine neue Größe umstellen.
                            desired = adaptive.sample() if fixed_workers is None else fixed_workers
                            if pool is None or desired != current_pool_size:
                                # Erst alle zuvor eingereihten Blöcke in Reihenfolge
                                # schreiben, bevor der Pool neu skaliert wird.
                                while pending:
                                    _check_cancel(cancel_event)
                                    raw_size, future = pending.popleft()
                                    codec, payload, digest = future.result()
                                    archive.write(struct.pack(">BII", codec, raw_size, len(payload)))
                                    archive.write(digest)
                                    archive.write(payload)
                                    processed_bytes += raw_size
                                    report_progress(name)
                                if pool is not None:
                                    pool.shutdown(wait=True)
                                # Frozen GUI apps must use freeze_support() from
                                # their guarded entry point before spawning workers.
                                # Native codecs release the GIL, so threads avoid
                                # launching duplicate GUI processes and stay fast.
                                pool = concurrent.futures.ThreadPoolExecutor(max_workers=desired)
                                current_pool_size = desired
                            chunk = stream.read(BLOCK_SIZE)
                            if not chunk:
                                break
                            if mode == "fast":
                                future = pool.submit(_encode_strategy_worker, chunk, strategy, level)
                            else:
                                future = pool.submit(_max_compress_worker, chunk, level, gpu_enabled)
                            pending.append((len(chunk), future))
                            if len(pending) >= desired * 3:
                                _check_cancel(cancel_event)
                                raw_size, future = pending.popleft()
                                codec, payload, digest = future.result()
                                archive.write(struct.pack(">BII", codec, raw_size, len(payload)))
                                archive.write(digest)
                                archive.write(payload)
                                processed_bytes += raw_size
                                report_progress(name)
                        while pending:
                            _check_cancel(cancel_event)
                            raw_size, future = pending.popleft()
                            codec, payload, digest = future.result()
                            archive.write(struct.pack(">BII", codec, raw_size, len(payload)))
                            archive.write(digest)
                            archive.write(payload)
                            processed_bytes += raw_size
                            report_progress(name)
                    archive.write(struct.pack(">B", 255))
                report_progress()
            finally:
                if pool is not None:
                    pool.shutdown(wait=True)
        os.replace(temp, output)
    except Exception:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def _read_exact(stream, length: int) -> bytes:
    data = stream.read(length)
    if len(data) != length:
        raise ArchiveError("Archiv unerwartet abgeschnitten")
    return data


class OperationCancelled(Exception):
    """Raised when the user cancels a long-running archive operation."""


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled("Vorgang wurde abgebrochen")


def _read_entries(stream):
    if _read_exact(stream, len(MAGIC)) != MAGIC:
        raise ArchiveError("Unbekanntes Archivformat")
    count, = struct.unpack(">I", _read_exact(stream, 4))
    if count > MAX_ENTRIES:
        raise ArchiveError("Eintragsanzahl überschreitet das Limit")
    seen: set[str] = set()
    for _ in range(count):
        name_len, original_size = struct.unpack(">HQ", _read_exact(stream, 10))
        if not 0 < name_len <= MAX_NAME or original_size > (1 << 63) - 1:
            raise ArchiveError("Ungültige Metadaten")
        try:
            name = _read_exact(stream, name_len).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ArchiveError("Ungültiger UTF-8-Pfad") from exc
        pure = PurePosixPath(name)
        if pure.is_absolute() or not name or ".." in pure.parts or "\\" in name or ":" in name:
            raise ArchiveError(f"Unsicherer Archivpfad: {name!r}")
        normalized = pure.as_posix()
        if normalized in seen:
            raise ArchiveError(f"Doppelter Archivpfad: {normalized}")
        seen.add(normalized)
        yield normalized, original_size


def list_archive(archive_path: Path) -> list[tuple[str, int]]:
    result = []
    with archive_path.open("rb") as stream:
        for name, size in _read_entries(stream):
            result.append((name, size))
            total = 0
            while True:
                codec, = struct.unpack(">B", _read_exact(stream, 1))
                if codec == 255:
                    break
                raw_size, packed_size = struct.unpack(">II", _read_exact(stream, 8))
                if codec not in CODECS or raw_size > MAX_BLOCK or packed_size > MAX_BLOCK + 1024 * 1024:
                    raise ArchiveError("Ungültiger Blockheader")
                _read_exact(stream, 32 + packed_size)
                total += raw_size
            if total != size:
                raise ArchiveError(f"Größenangabe stimmt nicht für {name}")
        if stream.read(1):
            raise ArchiveError("Unerwartete Daten am Archivende")
    return result


def extract_files(archive_path: Path, destination: Path, selected_names: set[str],
                 overwrite: bool = False, workers: int | str = "auto", cancel_event=None) -> None:
    """Entpackt ausgewählte Einträge; Integrität aller Blöcke wird geprüft."""
    destination = destination.resolve()
    fixed_workers = _validate_workers(workers)
    adaptive = AdaptiveWorkers(initial=fixed_workers)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=adaptive.current)
    try:
        destination.mkdir(parents=True, exist_ok=True)
        found: set[str] = set()
        with archive_path.open("rb") as stream:
            for name, original_size in _read_entries(stream):
                _check_cancel(cancel_event)
                target = (destination / Path(*PurePosixPath(name).parts)).resolve()
                if target != destination and destination not in target.parents:
                    raise ArchiveError(f"Unsicherer Zielpfad: {name}")
                should_write = name in selected_names
                if should_write:
                    found.add(name)
                    if target.exists() and not overwrite:
                        raise FileExistsError(f"Zieldatei existiert bereits: {target}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + ".pypack-tmp")
                writer = temp.open("wb") if should_write else None
                total = 0
                try:
                    pending = deque()
                    end_of_file = False
                    batch_size = max(4, min(16, adaptive.current))
                    while not end_of_file or pending:
                        _check_cancel(cancel_event)
                        while not end_of_file and len(pending) < adaptive.current * 3:
                            codec, = struct.unpack(">B", _read_exact(stream, 1))
                            if codec == 255:
                                end_of_file = True
                                break
                            raw_size, packed_size = struct.unpack(">II", _read_exact(stream, 8))
                            if codec not in CODECS or raw_size > MAX_BLOCK or packed_size > MAX_BLOCK + 1024 * 1024:
                                raise ArchiveError("Ungültiger Blockheader")
                            expected_hash = _read_exact(stream, 32)
                            payload = _read_exact(stream, packed_size)
                            pending.append((raw_size, (codec, payload, raw_size, expected_hash)))
                        if pending:
                            batch = [pending.popleft() for _ in range(min(batch_size, len(pending)))]
                            decoded_batches = pool.submit(_decompress_many_checked,
                                                         [item[1] for item in batch]).result()
                            for (raw_size, _), raw in zip(batch, decoded_batches):
                                if raw is None:
                                    raise ArchiveError(f"Prüfsummen- oder Größenfehler: {name}")
                                total += len(raw)
                                if total > original_size:
                                    raise ArchiveError(f"Datei größer als angegeben: {name}")
                                if writer:
                                    writer.write(raw)
                    if total != original_size:
                        raise ArchiveError(f"Dateigröße stimmt nicht: {name}")
                    if writer:
                        writer.close()
                        writer = None
                        os.replace(temp, target)
                except Exception:
                    if writer:
                        writer.close()
                    try:
                        temp.unlink()
                    except FileNotFoundError:
                        pass
                    raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    missing = selected_names - found
    if missing:
        raise ArchiveError("Ausgewählte Einträge fehlen im Archiv: " + ", ".join(sorted(missing)))


def unpack(archive_path: Path, destination: Path, overwrite: bool = False, test_only: bool = False,
           workers: int | str = "auto", cancel_event=None) -> None:
    destination = destination.resolve()
    fixed_workers = _validate_workers(workers)
    adaptive = AdaptiveWorkers(initial=fixed_workers)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=adaptive.current)
    try:
        if not test_only:
            destination.mkdir(parents=True, exist_ok=True)
        with archive_path.open("rb") as stream:
            for name, original_size in _read_entries(stream):
                _check_cancel(cancel_event)
                target = (destination / Path(*PurePosixPath(name).parts)).resolve()
                if target != destination and destination not in target.parents:
                    raise ArchiveError(f"Unsicherer Zielpfad: {name}")
                if not test_only:
                    if target.exists() and not overwrite:
                        raise FileExistsError(f"Zieldatei existiert bereits: {target}; nutze --overwrite")
                    target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + ".pypack-tmp")
                total = 0
                writer = None
                try:
                    if not test_only:
                        writer = temp.open("wb")
                    pending = deque()
                    end_of_file = False
                    batch_size = max(4, min(16, adaptive.current))
                    while not end_of_file or pending:
                        _check_cancel(cancel_event)
                        while not end_of_file and len(pending) < adaptive.current * 3:
                            codec, = struct.unpack(">B", _read_exact(stream, 1))
                            if codec == 255:
                                end_of_file = True
                                break
                            raw_size, packed_size = struct.unpack(">II", _read_exact(stream, 8))
                            if codec not in CODECS or raw_size > MAX_BLOCK or packed_size > MAX_BLOCK + 1024 * 1024:
                                raise ArchiveError("Ungültiger Blockheader")
                            expected_hash = _read_exact(stream, 32)
                            payload = _read_exact(stream, packed_size)
                            pending.append((raw_size, (codec, payload, raw_size, expected_hash)))
                        if pending:
                            batch = [pending.popleft() for _ in range(min(batch_size, len(pending)))]
                            decoded_batches = pool.submit(_decompress_many_checked,
                                                         [item[1] for item in batch]).result()
                            for (raw_size, _), raw in zip(batch, decoded_batches):
                                if raw is None:
                                    raise ArchiveError(f"Prüfsummen- oder Größenfehler: {name}")
                                total += len(raw)
                                if total > original_size:
                                    raise ArchiveError(f"Datei größer als angegeben: {name}")
                                if writer:
                                    writer.write(raw)
                    if total != original_size:
                        raise ArchiveError(f"Dateigröße stimmt nicht: {name}")
                    if writer:
                        writer.close()
                        writer = None
                        if target.exists() and not overwrite:
                            raise FileExistsError(f"Zieldatei existiert bereits: {target}")
                        os.replace(temp, target)
                except Exception:
                    if writer:
                        writer.close()
                    try:
                        temp.unlink()
                    except FileNotFoundError:
                        pass
                    raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _decompress_checked(codec: int, payload: bytes, raw_size: int, expected_hash: bytes):
    raw = _decompress(codec, payload, raw_size)
    if len(raw) != raw_size or hashlib.sha256(raw).digest() != expected_hash:
        return None
    return raw


def _decompress_many_checked(blocks):
    """Decode a small batch together, reducing per-block future overhead."""
    return [_decompress_checked(codec, payload, raw_size, digest)
            for codec, payload, raw_size, digest in blocks]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pypack", description="Adaptiver verlustfreier Dateikompressor")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack", help="Dateien oder Ordner archivieren")
    p.add_argument("inputs", nargs="+", type=Path)
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--level", type=int, choices=range(1, 10), default=6)
    p.add_argument("--mode", choices=("fast", "maximum"), default="fast",
                   help="fast: Strategie einmal pro Datei; maximum: beste Codec-Auswahl je Block")
    p.add_argument("--workers", default="auto",
                   help="Workerzahl (auto passt sie an CPU-Auslastung an; Standard: auto)")
    gpu_group = p.add_mutually_exclusive_group()
    gpu_group.add_argument("--gpu", action="store_true", help="GPU automatisch erkennen und falls geeignet mit CPU nutzen")
    gpu_group.add_argument("--cpu-only", action="store_true", help="GPU-Nutzung deaktivieren")
    for command in ("unpack", "test", "list"):
        p = sub.add_parser(command)
        p.add_argument("archive", type=Path)
        if command in {"unpack", "test"}:
            p.add_argument("--workers", default="auto", help="Workerzahl, Standard: auto")
        if command == "unpack":
            p.add_argument("-o", "--output", type=Path, default=Path("."))
            p.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "pack":
            workers = args.workers
            _validate_workers(workers)
            output = args.output or default_archive_name(args.inputs)
            use_gpu = False if args.cpu_only else None
            pack(args.inputs, output, args.level, workers, use_gpu=use_gpu, mode=args.mode)
            print(f"Archiv erstellt: {output}")
        elif args.command == "list":
            for name, size in list_archive(args.archive):
                print(f"{size:>12}  {name}")
        else:
            unpack(args.archive, getattr(args, "output", Path(".")),
                   getattr(args, "overwrite", False), test_only=args.command == "test",
                   workers=getattr(args, "workers", "auto"))
            print("Archiv ist intakt." if args.command == "test" else f"Entpackt nach: {args.output}")
    except (OSError, ValueError, ArchiveError, OperationCancelled) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())

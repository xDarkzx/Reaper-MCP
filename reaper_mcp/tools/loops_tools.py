"""Loop-library pipeline tools.

Scans a folder of audio loops, parses BPM / key / role from filenames,
and batch-loads the AI's selections into REAPER on auto-created tracks.
Designed for well-labelled sample packs (Prime Loops, Splice, Loopmasters,
Native Instruments Expansions, etc.) where metadata is encoded in names
like `Kick_140BPM_Am_01.wav` or `Deep Sub Bass 128 F#m Loop.wav`.

Typical AI workflow:
    1. scan_audio_folder("D:/loops/chillstep")  → 87 files, most 140 Am
    2. detect_common_bpm([picks…])              → 140
    3. transport_set_bpm(140)
    4. load_loops([{track_name:"Kick", file_path:…, position_sec:0}, …])

No librosa / soundfile requirement — filename parsing covers the 80%
case. Files without parseable metadata still get scanned; their fields
are just null and the AI can skip them.
"""

import json
import os
import re
from collections import Counter
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from reaper_mcp_shared.error_codes import ReaperMCPError, ErrorCode


AUDIO_EXTS = {".wav", ".mp3", ".flac", ".aif", ".aiff", ".ogg", ".m4a"}

# Role classification — maps loop filename keywords to a canonical role.
# Order matters: first match wins, so put specific before generic.
_ROLE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("kick",   ["kick", "bassdrum", "bd ", "bd_", "kik"]),
    ("snare",  ["snare", "snr", "sd ", "sd_", "clap", "rimshot", "rim"]),
    ("hat",    ["hat", "hh ", "hh_", "hi-hat", "hihat", "ohh", "chh", "closed hat", "open hat"]),
    ("ride",   ["ride", "crash", "cymbal"]),
    ("perc",   ["perc", "shaker", "tamb", "conga", "bongo", "cowbell"]),
    ("bass",   ["sub bass", "bass", "sub ", "808", "bassline", "reese"]),
    ("pad",    ["pad", "chord", "chords", "texture", "atmo", "atmos", "drone"]),
    ("lead",   ["lead", "melody", "mel ", "arp ", "arpeggio", "synth lead", "pluck"]),
    ("vocal",  ["vocal", "vox", "voc ", "voc_", "acapella", "chop"]),
    ("fx",     ["riser", "downlifter", "impact", "sweep", "whoosh", "uplifter", "fx"]),
    ("drums",  ["drum loop", "drumloop", "top loop", "beat", "full drum", "drums"]),
]

# `\b` doesn't help when underscores are used as separators (underscore is a
# word character in regex). Use explicit digit-boundary lookarounds instead
# and accept `_` / `-` / `.` / whitespace / edges as key-token boundaries.
_BPM_MARKED = re.compile(r"(?<!\d)(\d{2,3})\s*bpm", re.IGNORECASE)
_BPM_LIKELY = re.compile(r"(?<!\d)(\d{2,3})(?!\d)")
_KEY_STRICT = re.compile(
    r"(?:^|[_\-\s])([A-G])([#b♯♭])?(m|min|maj|Maj|MAJ)(?=[_\-\s.]|$)"
)
_KEY_LOOSE = re.compile(r"(?:^|[_\-\s])([A-G])([#b])(?=[_\-\s.]|$)")


def _parse_bpm(filename: str) -> int | None:
    """Extract BPM from a filename. First tries 'NNNbpm' markers, then any
    2-3 digit number in the plausible BPM range (60-220)."""
    m = _BPM_MARKED.search(filename)
    if m:
        bpm = int(m.group(1))
        if 60 <= bpm <= 220:
            return bpm
    # Fallback — any 2-3 digit number in range, first hit wins.
    for m in _BPM_LIKELY.finditer(filename):
        n = int(m.group(1))
        if 60 <= n <= 220:
            return n
    return None


def _parse_key(filename: str) -> str | None:
    """Extract musical key from a filename. Accepts:
      Am, Bbm, F#m, Cmaj, G#Maj, D#min, A_, C#_, etc.
    Returns a normalised key like 'Am', 'F#m', 'Cmaj'."""
    stem = filename.rsplit(".", 1)[0]

    def _norm(letter: str, acc: str | None, quality: str | None) -> str:
        acc = (acc or "").replace("♯", "#").replace("♭", "b")
        if quality:
            q = quality.lower()
            if q in ("m", "min"):
                return f"{letter}{acc}m"
            if q in ("maj",):
                return f"{letter}{acc}maj"
        return f"{letter}{acc}"

    m = _KEY_STRICT.search(stem)
    if m:
        return _norm(m.group(1), m.group(2), m.group(3))
    m = _KEY_LOOSE.search(stem)
    if m:
        # Loose match requires an accidental (F# / Bb / etc.) for confidence.
        return _norm(m.group(1), m.group(2), None)
    return None


def _parse_role(filename: str) -> str | None:
    """Classify the loop's role (kick/bass/pad/lead/…) by keyword match."""
    name = " " + filename.lower().replace("_", " ").replace("-", " ") + " "
    for role, keywords in _ROLE_KEYWORDS:
        for kw in keywords:
            kw_padded = kw if kw.startswith(" ") or kw.endswith(" ") else f" {kw} "
            if kw.endswith(" ") or kw.endswith("_"):
                kw_padded = f" {kw.rstrip(' _')}"
            if kw_padded in name or f" {kw}" in name:
                return role
    return None


def _duration_seconds(path: Path) -> float | None:
    """Return audio duration if obtainable without heavy deps.

    Uses soundfile if the [analysis] extras are installed, else falls back
    to the stdlib `wave` module for .wav files only. Returns None otherwise.
    """
    try:
        import soundfile as sf
        return float(sf.info(str(path)).duration)
    except ImportError:
        pass
    except Exception:
        return None

    if path.suffix.lower() == ".wav":
        try:
            import wave
            with wave.open(str(path), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                if rate > 0:
                    return frames / float(rate)
        except Exception:
            return None
    return None


def _safe_folder(path: str) -> Path:
    if not path or not path.strip():
        raise ReaperMCPError(ErrorCode.INVALID_PATH, "folder path is required")
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise ReaperMCPError(ErrorCode.INVALID_PATH, f"Folder not found: {p}")
    if not p.is_dir():
        raise ReaperMCPError(ErrorCode.INVALID_PATH, f"Not a directory: {p}")
    return p


def register(mcp: FastMCP):
    from reaper_mcp.main import client

    @mcp.tool()
    async def scan_audio_folder(
        path: str,
        recursive: bool = True,
        max_files: int = 500,
    ) -> dict:
        """Walk a folder for audio loops and parse metadata from filenames.

        Returns every audio file (.wav, .mp3, .flac, .aif, .aiff, .ogg, .m4a)
        with BPM, musical key, and role (kick / bass / pad / lead / fx / …)
        extracted from the filename. Plus a `summary` of distributions so
        the AI can quickly decide on a target BPM / key before picking loops.

        Args:
            path: Absolute folder path (e.g., `D:/Music Production/Chillstep Express`).
            recursive: Walk subfolders too. Default True.
            max_files: Stop after this many files. Default 500; max 5000.

        Returns a structure with:
          - folder: resolved absolute path
          - total_files: how many matched
          - truncated: True if max_files hit before end
          - summary: BPM / key / role distributions + parse-failure counts
          - loops: list of { path, filename, duration_sec, size_mb,
                             parsed: { bpm, key, role } }
          - hint: a one-line suggestion for the AI's next call

        Files without parseable metadata are still listed; their fields
        are null. Pair with `transport_set_bpm` + `load_loops` to turn the
        selection into a working REAPER session.
        """
        if not 1 <= max_files <= 5000:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "max_files must be 1-5000")

        folder = _safe_folder(path)

        loops: list[dict] = []
        truncated = False

        walker = folder.rglob("*") if recursive else folder.iterdir()
        try:
            for p in walker:
                if not p.is_file():
                    continue
                if p.suffix.lower() not in AUDIO_EXTS:
                    continue
                if len(loops) >= max_files:
                    truncated = True
                    break
                try:
                    size_mb = round(p.stat().st_size / 1_048_576, 3)
                except OSError:
                    size_mb = None
                loops.append({
                    "path": str(p),
                    "filename": p.name,
                    "duration_sec": _duration_seconds(p),
                    "size_mb": size_mb,
                    "parsed": {
                        "bpm": _parse_bpm(p.name),
                        "key": _parse_key(p.name),
                        "role": _parse_role(p.name),
                    },
                })
        except PermissionError as e:
            raise ReaperMCPError(
                ErrorCode.COMMAND_FAILED,
                f"Permission denied while scanning: {e}",
            )

        bpms = [l["parsed"]["bpm"] for l in loops if l["parsed"]["bpm"]]
        keys = [l["parsed"]["key"] for l in loops if l["parsed"]["key"]]
        roles = [l["parsed"]["role"] for l in loops if l["parsed"]["role"]]

        no_bpm = sum(1 for l in loops if not l["parsed"]["bpm"])
        no_key = sum(1 for l in loops if not l["parsed"]["key"])

        summary = {
            "bpm_distribution": dict(Counter(bpms).most_common(5)),
            "key_distribution": dict(Counter(keys).most_common(5)),
            "role_distribution": dict(Counter(roles).most_common()),
            "files_without_parsed_bpm": no_bpm,
            "files_without_parsed_key": no_key,
        }

        if not loops:
            hint = f"No audio files found under {folder}. Check the path or try recursive=True."
        elif bpms:
            top_bpm, top_count = Counter(bpms).most_common(1)[0]
            top_key = Counter(keys).most_common(1)[0][0] if keys else "unknown"
            hint = (
                f"Found {len(loops)} loops. Dominant tempo {top_bpm} BPM ({top_count} files), "
                f"dominant key {top_key}. Pick loops in that cluster, then call "
                f"transport_set_bpm({top_bpm}) and load_loops(...)."
            )
        else:
            hint = (
                f"Found {len(loops)} loops but no BPM found in any filename. "
                f"Either set project BPM manually or use analyze_loudness on a few "
                f"files to decide."
            )

        return {
            "folder": str(folder),
            "total_files": len(loops),
            "truncated": truncated,
            "summary": summary,
            "loops": loops,
            "hint": hint,
        }

    @mcp.tool()
    async def detect_common_bpm(file_paths: str) -> dict:
        """Given a JSON array of file paths, return the most common BPM
        parsed from their filenames.

        Useful after `scan_audio_folder` when the AI has narrowed down a set
        of candidate loops and wants to confirm they agree on tempo before
        setting the project BPM.

        Args:
            file_paths: JSON array of absolute paths.

        Returns:
            detected_bpm: the most common value (int), or None if none found.
            bpm_votes: full distribution of BPMs across the set.
            confidence: fraction of files that agreed with the winner.
            hint: a one-line next-step suggestion.
        """
        try:
            paths = json.loads(file_paths)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"file_paths must be a JSON array: {e.msg}",
            )
        if not isinstance(paths, list):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "file_paths must be a JSON array")
        if len(paths) > 1000:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "file_paths max length is 1000")

        bpms = []
        for p in paths:
            if not isinstance(p, str):
                continue
            bpm = _parse_bpm(Path(p).name)
            if bpm:
                bpms.append(bpm)

        if not bpms:
            return {
                "detected_bpm": None,
                "bpm_votes": {},
                "sample_size": 0,
                "total_input": len(paths),
                "confidence": 0.0,
                "hint": (
                    "No BPM found in any filename. Set project BPM manually via "
                    "transport_set_bpm, then load the loops."
                ),
            }

        votes = Counter(bpms)
        top_bpm, top_count = votes.most_common(1)[0]
        return {
            "detected_bpm": top_bpm,
            "bpm_votes": dict(votes.most_common()),
            "sample_size": len(bpms),
            "total_input": len(paths),
            "confidence": round(top_count / len(bpms), 3),
            "hint": f"Set project to {top_bpm} BPM — {top_count}/{len(bpms)} files agree.",
        }

    @mcp.tool()
    async def load_loops(loops: str, project_bpm: float = 0.0) -> dict:
        """Batch-load audio loops into REAPER, auto-creating tracks by name.

        For each entry in the JSON array, find the named track (or create
        it if missing) and insert the audio file at the given position.
        Optionally sets the project BPM first so the loops align with the
        grid.

        Args:
            loops: JSON array of entries. Each entry is an object with:
                - track_name (required): name of the destination track.
                  Case-sensitive match against existing tracks; if no match,
                  a new track is created with this name.
                - file_path (required): absolute path to the audio file.
                - position_sec (optional, default 0.0): start position in
                  seconds within the project.
            project_bpm: If > 0, call transport_set_bpm before inserting
                media so the project's tempo grid is correct.

        Returns a summary with tracks created vs reused, loops loaded, and
        per-entry errors (missing files, invalid entries) so the AI can
        recover without blowing up the whole batch.
        """
        try:
            loop_list = json.loads(loops)
        except json.JSONDecodeError as e:
            raise ReaperMCPError(
                ErrorCode.INVALID_PARAMETER,
                f"loops must be a JSON array: {e.msg}",
            )
        if not isinstance(loop_list, list):
            raise ReaperMCPError(ErrorCode.INVALID_PARAMETER, "loops must be a JSON array")
        if len(loop_list) > 100:
            raise ReaperMCPError(
                ErrorCode.VALUE_OUT_OF_RANGE,
                f"Too many loops ({len(loop_list)}) in one call — max 100",
            )

        if project_bpm < 0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "project_bpm must be >= 0")
        if project_bpm > 0 and not 40.0 <= project_bpm <= 300.0:
            raise ReaperMCPError(ErrorCode.VALUE_OUT_OF_RANGE, "project_bpm must be 40-300")

        bpm_set = False
        if project_bpm > 0:
            await client.execute("transport_set_bpm", bpm=project_bpm)
            bpm_set = True

        tracks_result = await client.execute("track_get_all")
        data = tracks_result.get("data", tracks_result)
        tracks_list = data.get("tracks", [])
        existing: dict[str, int] = {}
        for t in tracks_list:
            name = t.get("name", "")
            idx = t.get("index", t.get("track_index"))
            if name and idx is not None:
                existing[name] = int(idx)

        created: list[str] = []
        loaded: list[dict] = []
        errors: list[dict] = []

        for i, entry in enumerate(loop_list):
            if not isinstance(entry, dict):
                errors.append({"index": i, "error": "entry must be an object"})
                continue
            track_name = str(entry.get("track_name", "")).strip()
            file_path = str(entry.get("file_path", "")).strip()
            position_sec = float(entry.get("position_sec", 0.0))

            if not track_name:
                errors.append({"index": i, "error": "track_name is required"})
                continue
            if not file_path:
                errors.append({"index": i, "error": "file_path is required"})
                continue
            if position_sec < 0:
                errors.append({"index": i, "error": "position_sec must be >= 0"})
                continue
            if not os.path.isfile(file_path):
                errors.append({
                    "index": i,
                    "track_name": track_name,
                    "error": f"File not found: {file_path}",
                })
                continue

            if track_name in existing:
                track_idx = existing[track_name]
            else:
                result = await client.execute("track_create", name=track_name)
                new_idx = result.get("index", result.get("track_index"))
                if new_idx is None:
                    errors.append({
                        "index": i,
                        "track_name": track_name,
                        "error": "track_create returned no index",
                    })
                    continue
                track_idx = int(new_idx)
                existing[track_name] = track_idx
                created.append(track_name)

            try:
                await client.execute(
                    "item_insert_media",
                    track_index=track_idx,
                    path=file_path,
                    position=position_sec,
                )
                loaded.append({
                    "track_name": track_name,
                    "track_index": track_idx,
                    "file": os.path.basename(file_path),
                    "position_sec": position_sec,
                })
            except Exception as e:
                errors.append({
                    "index": i,
                    "track_name": track_name,
                    "error": f"item_insert_media failed: {e}",
                })

        if errors and not loaded:
            hint = f"All {len(loop_list)} entries failed. First error: {errors[0].get('error')}"
        elif errors:
            hint = (
                f"Loaded {len(loaded)} loops across {len(created)} new track(s); "
                f"{len(errors)} entries failed (see `errors`). "
                f"Consider engine_mix(style=...) and then project_export_audio to render."
            )
        elif loaded:
            hint = (
                f"Loaded {len(loaded)} loops across {len(created)} new track(s). "
                f"Hit transport_play, or run engine_mix(style=...) + engine_master(style=...) "
                f"to mix and master the arrangement."
            )
        else:
            hint = "No loops loaded and no errors — loops array was empty?"

        return {
            "project_bpm_set": bpm_set,
            "project_bpm": project_bpm if bpm_set else None,
            "tracks_created": created,
            "tracks_reused": [l["track_name"] for l in loaded if l["track_name"] not in created],
            "loops_loaded": len(loaded),
            "details": loaded,
            "errors": errors,
            "hint": hint,
        }

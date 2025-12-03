#!/usr/bin/env python3
"""
organize_desktop.py
Move files from a source folder into categorized folders.

Usage:
    python organize_desktop.py --source ~/Desktop --dry-run
    python organize_desktop.py --source ~/Downloads --undo
"""

from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path
import json
import logging
from datetime import datetime

# Configure logger
logger = logging.getLogger("organize")
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Default categories: extension -> folder name
CATEGORIES = {
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp"},
    "Documents": {".pdf", ".docx", ".doc", ".txt", ".md", ".pptx", ".xlsx", ".csv"},
    "Archives": {".zip", ".tar", ".gz", ".rar", ".7z"},
    "Code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rb", ".rs"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a"},
    "Video": {".mp4", ".mkv", ".mov", ".avi"},
    "Installers": {".exe", ".msi", ".dmg", ".deb", ".apk"}
}

METADATA_FILE = ".organize_history.json"


def which_category(ext: str) -> str | None:
    ext = ext.lower()
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return None


def build_args():
    p = argparse.ArgumentParser(description="Organize files in a folder by category.")
    p.add_argument("--source", "-s", type=Path, default=Path.home() / "Desktop",
                   help="Source folder to organize (default: ~/Desktop)")
    p.add_argument("--dest", "-d", type=Path, default=None,
                   help="Optional target parent folder. If omitted, subfolders are created in source.")
    p.add_argument("--dry-run", action="store_true", help="Show what will happen but don't move files.")
    p.add_argument("--undo", action="store_true", help="Undo last run (uses metadata file).")
    p.add_argument("--by-date", action="store_true",
                   help="Also bucket into YYYY-MM subfolders inside each category by modified time.")
    p.add_argument("--min-size-kb", type=int, default=0, help="Ignore files smaller than this (KB).")
    return p.parse_args()


def safe_move(src: Path, dest: Path, dry_run: bool):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        logger.info(f"DRY: would move {src} -> {dest}")
    else:
        # If dest exists, append counter
        final = dest
        counter = 1
        while final.exists():
            final = dest.with_name(f"{dest.stem}_{counter}{dest.suffix}")
            counter += 1
        shutil.move(str(src), str(final))
        logger.info(f"Moved {src.name} -> {final}")
        return final
    return None


def run_organize(source: Path, dest_parent: Path | None, dry_run: bool, by_date: bool, min_size_kb: int):
    source = source.expanduser().resolve()
    if dest_parent:
        dest_parent = dest_parent.expanduser().resolve()
    else:
        dest_parent = source

    if not source.is_dir():
        logger.error(f"Source {source} is not a directory.")
        sys.exit(1)

    moves = []  # records of (from, to)
    for item in source.iterdir():
        if item.is_dir():
            # skip folders we created earlier (best-effort: skip known categories)
            if item.name in CATEGORIES.keys():
                logger.debug(f"Skipping category folder {item.name}")
                continue
            if item.name == METADATA_FILE:
                continue
            continue  # don't recurse into folders

        if item.stat().st_size < min_size_kb * 1024:
            logger.debug(f"Skipping small file {item.name}")
            continue

        category = which_category(item.suffix)
        folder_name = category if category else "Other"
        target_parent = dest_parent / folder_name
        if by_date:
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            sub = f"{mtime.year}-{mtime.month:02d}"
            target_parent = target_parent / sub

        target_parent.mkdir(parents=True, exist_ok=True)
        target = target_parent / item.name

        final = safe_move(item, target, dry_run)
        if final:
            moves.append({"from": str(item), "to": str(final)})
        else:
            # dry run: record intended move
            moves.append({"from": str(item), "to": str(target), "dry_run": True})

    # Save history for undo (append timestamped entry)
    history_path = source / METADATA_FILE
    if dry_run:
        logger.info("Dry-run completed. No changes saved.")
    else:
        history = {"timestamp": datetime.utcnow().isoformat(), "moves": moves}
        if history_path.exists():
            try:
                o = json.loads(history_path.read_text())
            except Exception:
                o = []
            if isinstance(o, list):
                o.append(history)
            else:
                o = [o, history]
        else:
            o = [history]
        history_path.write_text(json.dumps(o, indent=2))
        logger.info(f"Saved history to {history_path}")


def run_undo(source: Path):
    source = source.expanduser().resolve()
    history_path = source / METADATA_FILE
    if not history_path.exists():
        logger.error("No history file found to undo.")
        return

    data = json.loads(history_path.read_text())
    if not isinstance(data, list) or not data:
        logger.error("History file corrupt or empty.")
        return
    last = data.pop()  # last run
    moves = last.get("moves", [])
    # Reverse moves: move 'to' back to 'from' if present
    for m in reversed(moves):
        frm = Path(m.get("to"))
        to = Path(m.get("from"))
        if frm.exists():
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(frm), str(to))
            logger.info(f"Restored {frm.name} -> {to}")
        else:
            logger.warning(f"Expected file to restore not found: {frm}")

    # write back history
    history_path.write_text(json.dumps(data, indent=2))
    logger.info("Undo complete.")


def main():
    args = build_args()

    if args.undo:
        run_undo(args.source)
        return

    logger.info(f"Organizing: source={args.source}, dest_parent={args.dest}, dry_run={args.dry_run}")
    run_organize(args.source, args.dest, args.dry_run, args.by_date, args.min_size_kb)


if __name__ == "__main__":
    main()

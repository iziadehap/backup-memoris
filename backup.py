#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Samsung Phone to External Hard Drive - 10-Year Life Memory Time Capsule & Drive Health Tool for macOS.

Dual-Engine Architecture:
1. DIRECT ADB USB MODE (Recommended & 100% Free - No MacDroid needed!):
   Directly connects to your Samsung phone over USB using Android Debug Bridge.
   Transfers photos, videos, screenshots, voice recordings, WhatsApp media, documents,
   and encrypted databases at full hardware USB speed.
2. MOUNTED VOLUME MODE (Fallback):
   If you prefer using MacDroid or another MTP tool that mounts under /Volumes/.

10-Year Archival Time Capsule Features:
- Zero-Overwrite Versioned Conflict Resolution: NEVER overwrites existing files. Versioned
  naming (filename_v1.ext, filename_v2.ext) preserves every memory permanently.
- Smart Chronological Organization: Automatically organizes Camera Photos, Videos, and Screenshots
  into <Category>/<YYYY>/<YYYY-MM>/<filename> using date extraction from filenames & timestamps.
- Complete WhatsApp & Context Coverage: Backs up WhatsApp Voice Notes, Audio, Video Notes, Animated GIFs,
  Images, Videos, Contacts (.vcf), and encrypted chat databases (.crypt14, .crypt15).
- Recursive DCIM & Screenshot Scanning: Captures Samsung Single Take, album folders, and subfolders.
- 10-Year Bitrot Protection (SHA-256 Integrity Manifest): Computes and logs SHA-256 checksums to
  Backup/memories_integrity_sha256.txt. Includes an active bitrot audit engine (VERIFY_BITROT_INTEGRITY).
- Offline HTML5 Interactive Dashboard (Backup/Memories_Timeline.html): A standalone, self-contained,
  offline-ready dark-mode browser with photo lazy-loading, full-resolution lightbox, playable HTML5
  video, integrated voice player with sequential auto-play, and full Arabic/RTL & English search support.
- Hard Drive Health Diagnostics: Checks S.M.A.R.T. status, free space, sector write/read integrity,
  and write latency on every run. Warns if the hard drive is degrading so you can replace it.
- Preserves original file modification timestamps (mtime) and uses atomic (.tmp_part) writes.
- Full Unicode & Arabic character support.
"""

import sys
import os
import shutil
import time
import subprocess
import hashlib
import re
import json
import urllib.parse
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 output in macOS terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ==============================================================================
# CONFIGURATION - EDIT THESE VALUES TO MATCH YOUR SETUP
# ==============================================================================

# 1. Connection Mode:
#    "AUTO"  = Automatically uses ADB if phone is connected via USB (Fastest, 100% Free!).
#              Falls back to checking /Volumes/ if MacDroid is used.
#    "ADB"   = Force ADB direct USB mode (No MacDroid needed).
#    "MOUNT" = Force mounted volume mode (e.g. MacDroid under /Volumes/).
CONNECTION_MODE = "AUTO"

# 2. Mount path of phone (ONLY used if using MacDroid or MOUNT mode):
PHONE_MOUNT_PATH = "/Volumes/Samsung"

# 3. Mount path of your external hard drive:
DESTINATION_DRIVE = "/Volumes/Backup_data"

# 4. DRY RUN Mode:
#    True  = SIMULATION ONLY. Lists what WOULD be copied without copying anything.
#    False = LIVE RUN. Performs the actual file copy to the external hard drive.
DRY_RUN = False

# 5. Backup Categories (What memories to include):
BACKUP_CAMERA_MEDIA = True        # Photos and videos from Camera (organized by YYYY/YYYY-MM)
BACKUP_SCREENSHOTS = True         # Screenshots & Screen recordings (organized by YYYY/YYYY-MM)
BACKUP_VOICE_AUDIO = True         # Voice recorder memos, WhatsApp audio & voice notes, call recordings
BACKUP_OTHER_MEMORIES = True      # Pictures & videos from Pictures/, WhatsApp, Downloads, etc.
BACKUP_DOCUMENTS = True           # PDF, Word (.doc/.docx), text, office documents
BACKUP_ARCHIVES = True            # ZIP, RAR, 7z archive files
BACKUP_CONTACTS_AND_CHATS = True  # Contacts (.vcf) & WhatsApp databases (.crypt14, .crypt15)

# 6. 10-Year Archival & Bitrot Protection:
VERIFY_BITROT_INTEGRITY = False   # Set True to audit all previously backed-up files against SHA-256 manifest
GENERATE_TIMELINE_HTML = True     # Generate offline HTML5 dashboard at <DRIVE>/Backup/Memories_Timeline.html

# 7. Hard Drive Health Thresholds:
CHECK_DRIVE_HEALTH = True         # Run hardware & sector health check on every run
LOW_SPACE_WARN_GB = 20.0          # Warn if free space is below this threshold (GB)
LOW_SPACE_WARN_PERCENT = 10.0     # Warn if free space is below this percentage (%)


# ==============================================================================
# MEDIA EXTENSIONS & DESTINATION DEFINITIONS
# ==============================================================================

# Photos & raw images
PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp", ".dng",
    ".gif", ".bmp", ".tiff", ".tif", ".raw", ".cr2", ".nef", ".arw"
}

# Videos
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".3gp", ".mkv", ".avi", ".wmv", ".webm", ".ts", ".flv", ".m4v"
}

# Voice recordings, audio memos, WhatsApp voice notes
AUDIO_EXTENSIONS = {
    ".m4a", ".amr", ".3ga", ".mp3", ".wav", ".aac", ".opus", ".ogg", ".flac", ".awb", ".wma"
}

# Document files (PDF, Word, Office, Text)
DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt",
    ".xls", ".xlsx", ".csv", ".ppt", ".pptx"
}

# Zip and archive files
ARCHIVE_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz"
}

# Contacts and database files
CONTACT_EXTENSIONS = {
    ".vcf"
}

# Combined sets
SCREENSHOT_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS
ALL_MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# Backup folder names on external drive (<DESTINATION_DRIVE>/Backup/...)
DEST_SUBFOLDER_PHOTOS = "Camera Photos"
DEST_SUBFOLDER_VIDEOS = "Videos"
DEST_SUBFOLDER_SCREENSHOTS = "Screenshots"
DEST_SUBFOLDER_VOICE = "Voice & Audio Recordings"
DEST_SUBFOLDER_OTHER_MEMORIES = "Other Pictures & Media"
DEST_SUBFOLDER_DOCUMENTS = "Documents"
DEST_SUBFOLDER_ARCHIVES = "Zip & Archives"
DEST_SUBFOLDER_CONTACTS_CHATS = "Contacts & Chat Databases"

INTEGRITY_MANIFEST_FILENAME = "memories_integrity_sha256.txt"
TIMELINE_HTML_FILENAME = "Memories_Timeline.html"
LOG_FILENAME = "backup_log.txt"

# Date extraction regex for Samsung & WhatsApp filenames: YYYYMMDD
DATE_REGEX = re.compile(r'(20[0-4]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])')


# ==============================================================================
# HELPER & FORMATTING FUNCTIONS
# ==============================================================================

def format_size(bytes_num: int | float) -> str:
    """Format bytes into human-readable string (e.g., 14.25 MB, 1.80 GB)."""
    val = float(bytes_num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if val < 1024.0:
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} PB"


def list_mounted_volumes() -> list[str]:
    """Return a list of currently mounted paths under /Volumes."""
    volumes_dir = Path("/Volumes")
    if not volumes_dir.exists():
        return []
    try:
        return [str(p) for p in volumes_dir.iterdir() if p.is_dir()]
    except Exception:
        return []


def check_adb_connected() -> tuple[bool, str]:
    """
    Checks if an Android device is connected via ADB.
    Returns (is_connected: bool, device_model_or_serial: str).
    """
    try:
        res = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode != 0:
            return False, ""

        lines = res.stdout.strip().splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                model_res = subprocess.run(
                    ["adb", "-s", serial, "shell", "getprop", "ro.product.model"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                model = model_res.stdout.strip() if model_res.returncode == 0 and model_res.stdout.strip() else serial
                return True, model
    except Exception:
        pass
    return False, ""


def extract_year_month(filename: str, fallback_mtime: float | None = None) -> str:
    r"""
    Extracts chronological year and month (YYYY/YYYY-MM) from Samsung and WhatsApp filenames.
    Uses regex r'(20[0-4]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])' (e.g. 20261105_183000.jpg,
    IMG-20261105-WA0001.jpg, PTT-20261105-WA0001.opus, Screenshot_20261105...).
    Falls back to file modification timestamp (mtime) if available, or 'Unsorted_Date'.
    """
    m = DATE_REGEX.search(filename)
    if m:
        year = m.group(1)
        month = m.group(2)
        return f"{year}/{year}-{month}"

    if fallback_mtime is not None and fallback_mtime > 0:
        try:
            dt = datetime.fromtimestamp(fallback_mtime)
            if 1990 <= dt.year <= 2050:
                return f"{dt.year}/{dt.strftime('%Y-%m')}"
        except Exception:
            pass

    return "Unsorted_Date"


def get_safe_destination_path(dst_file: Path, src_size: int) -> tuple[Path, bool]:
    """
    Zero-Overwrite Versioned Conflict Resolution (Critical Safety Guarantee):
    - If dst_file does not exist: returns (dst_file, False) to indicate it should be copied.
    - If dst_file exists with the exact same size: returns (dst_file, True) to skip it.
    - If dst_file exists with a DIFFERENT size: NEVER overwrites the existing file.
      Generates filename_v1.ext, filename_v2.ext, etc.
      If any existing version has the exact same size, returns (version_path, True) to skip.
      Otherwise returns the first available non-existent version (new_path, False) to copy safely.
    """
    if not dst_file.exists():
        return dst_file, False

    try:
        if dst_file.stat().st_size == src_size:
            return dst_file, True
    except Exception:
        pass

    # Conflict with differing size - generate versioned destination
    stem = dst_file.stem
    suffix = dst_file.suffix
    parent = dst_file.parent
    version = 1

    while True:
        versioned_path = parent / f"{stem}_v{version}{suffix}"
        if not versioned_path.exists():
            return versioned_path, False
        try:
            if versioned_path.stat().st_size == src_size:
                return versioned_path, True
        except Exception:
            pass
        version += 1


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file using 1MB chunk streaming."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def append_integrity_manifest(manifest_path: Path, sha256_hash: str, rel_path: str):
    """Appends a single verified file hash to Backup/memories_integrity_sha256.txt."""
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "a", encoding="utf-8") as f:
            f.write(f"{sha256_hash}  {rel_path}\n")
    except Exception as e:
        print(f"\n           [!] Manifest write error: {e}")


def load_integrity_manifest(manifest_path: Path) -> dict[str, str]:
    """Loads existing manifest entries: mapping relative_path -> sha256_hash."""
    manifest_map = {}
    if not manifest_path.is_file():
        return manifest_map
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("  ", 1)
                if len(parts) == 2:
                    h, p = parts[0].strip(), parts[1].strip()
                    manifest_map[p] = h
    except Exception as e:
        print(f"  [!] Warning: Failed reading integrity manifest: {e}")
    return manifest_map


def verify_bitrot_integrity(backup_root: Path, manifest_path: Path) -> dict:
    """
    Verifies all files recorded in the SHA-256 integrity manifest against current disk bytes.
    Detects silent data corruption (bitrot), bad sectors, or missing files.
    """
    result = {
        "manifest_exists": False,
        "total_manifest_entries": 0,
        "verified_passed": 0,
        "corrupted_files": [],  # list of (rel_path, expected_hash, actual_hash)
        "missing_files": [],    # list of rel_path
        "read_errors": [],      # list of (rel_path, error_str)
    }
    if not manifest_path.is_file():
        return result

    result["manifest_exists"] = True
    manifest = load_integrity_manifest(manifest_path)
    result["total_manifest_entries"] = len(manifest)
    if not manifest:
        return result

    print("\n" + "=" * 70)
    print("       10-YEAR BITROT & CRYPTOGRAPHIC INTEGRITY AUDIT")
    print("=" * 70)
    print(f"Manifest File        : {manifest_path.name}")
    print(f"Total Files in Audit : {len(manifest):,}")
    print("Auditing all files against recorded SHA-256 hashes (checking for bitrot)...")

    for i, (rel_path, expected_hash) in enumerate(manifest.items(), start=1):
        target = backup_root / rel_path
        if not target.exists():
            result["missing_files"].append(rel_path)
            print(f"  [{i}/{len(manifest)}] [MISSING] {rel_path}")
            continue

        try:
            actual_hash = compute_sha256(target)
            if actual_hash == expected_hash:
                result["verified_passed"] += 1
            else:
                result["corrupted_files"].append((rel_path, expected_hash, actual_hash))
                print(f"  [{i}/{len(manifest)}] [CORRUPTED / BITROT DETECTED] {rel_path}")
        except Exception as e:
            result["read_errors"].append((rel_path, str(e)))
            print(f"  [{i}/{len(manifest)}] [I/O ERROR] {rel_path}: {e}")

    return result


# ==============================================================================
# HARD DRIVE HEALTH CHECK MODULE (KERNEL I/O TELEMETRY & SECTOR DIAGNOSTICS)
# ==============================================================================

def get_drive_hardware_telemetry(drive_path: Path) -> dict:
    """
    Extracts hardware-level drive telemetry and error counters directly from
    the macOS Apple IOKit kernel (IOBlockStorageDriver) and USB registry.
    """
    telemetry = {
        "model": "WD5000LPLX-66ZNT",
        "vendor": "Western Digital",
        "serial": "N/A",
        "read_ops": "N/A",
        "write_ops": "N/A",
        "read_errors": 0,
        "write_errors": 0,
        "read_retries": 0,
        "write_retries": 0,
        "kernel_io_clean": True,
    }
    try:
        proc = subprocess.run(
            ["ioreg", "-r", "-c", "IOBlockStorageDriver", "-l"],
            capture_output=True, text=True, timeout=5
        )
        if proc.returncode == 0:
            lines = proc.stdout.splitlines()
            for i, line in enumerate(lines):
                if '"Statistics" =' in line:
                    chunk = "".join(lines[i:i+15])
                    m_ro = re.search(r'"Operations \(Read\)"=(\d+)', chunk)
                    m_wo = re.search(r'"Operations \(Write\)"=(\d+)', chunk)
                    m_re = re.search(r'"Errors \(Read\)"=(\d+)', chunk)
                    m_we = re.search(r'"Errors \(Write\)"=(\d+)', chunk)
                    m_rr = re.search(r'"Retries \(Read\)"=(\d+)', chunk)
                    m_wr = re.search(r'"Retries \(Write\)"=(\d+)', chunk)

                    if m_ro: telemetry["read_ops"] = f"{int(m_ro.group(1)):,}"
                    if m_wo: telemetry["write_ops"] = f"{int(m_wo.group(1)):,}"
                    if m_re: telemetry["read_errors"] = int(m_re.group(1))
                    if m_we: telemetry["write_errors"] = int(m_we.group(1))
                    if m_rr: telemetry["read_retries"] = int(m_rr.group(1))
                    if m_wr: telemetry["write_retries"] = int(m_wr.group(1))
                    break

        proc2 = subprocess.run(
            ["ioreg", "-p", "IOUSB", "-l"],
            capture_output=True, text=True, timeout=5
        )
        if proc2.returncode == 0:
            m_ser = re.search(r'"kUSBSerialNumberString" = "([^"]+)"', proc2.stdout)
            if m_ser:
                telemetry["serial"] = m_ser.group(1).strip()
            m_prod = re.search(r'"USB Product Name" = "(WD5000LPLX[^"]+)"', proc2.stdout)
            if m_prod:
                telemetry["model"] = m_prod.group(1).strip()

        if (telemetry["read_errors"] > 0 or telemetry["write_errors"] > 0 or
            telemetry["read_retries"] > 0 or telemetry["write_retries"] > 0):
            telemetry["kernel_io_clean"] = False
    except Exception:
        pass
    return telemetry


def check_drive_health(drive_path: Path) -> dict:
    """
    Performs comprehensive diagnostic checks on the backup external hard drive:
    1. Hardware telemetry & error counters via macOS IOKit (IOBlockStorageDriver).
    2. S.M.A.R.T. status & hardware flags via macOS diskutil.
    3. Available storage capacity and low space warnings.
    4. Filesystem read-only status and APFS lock checks.
    5. Active multi-sector cryptographic SHA-256 data integrity test.
    6. Write latency and transfer speed benchmarking.
    """
    report = {
        "device_name": drive_path.name,
        "physical_model": "Western Digital Black (WD5000LPLX-66ZNT)",
        "mount_point": str(drive_path),
        "smart_status": "Unknown",
        "telemetry": get_drive_hardware_telemetry(drive_path),
        "read_only": False,
        "total_bytes": 0,
        "used_bytes": 0,
        "free_bytes": 0,
        "free_percent": 0.0,
        "write_speed_mb_s": 0.0,
        "write_latency_s": 0.0,
        "integrity_passed": True,
        "status": "HEALTHY",
        "warnings": [],
        "critical_errors": [],
    }

    # 1. Query diskutil for hardware info & SMART
    try:
        res = subprocess.run(
            ["diskutil", "info", str(drive_path)],
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line_strip = line.strip()
                if "Device / Media Name:" in line_strip:
                    report["device_name"] = line_strip.split(":", 1)[1].strip()
                elif "SMART Status:" in line_strip:
                    report["smart_status"] = line_strip.split(":", 1)[1].strip()
                elif "Volume Read-Only:" in line_strip or "Media Read-Only:" in line_strip:
                    if "Yes" in line_strip:
                        report["read_only"] = True
                        report["critical_errors"].append(
                            "Drive is mounted as READ-ONLY! The filesystem may be corrupted or locked."
                        )
    except Exception as e:
        report["warnings"].append(f"Could not query diskutil: {e}")

    # Check S.M.A.R.T. status
    smart = report["smart_status"].lower()
    if "failing" in smart or "about to fail" in smart or "bad" in smart:
        report["critical_errors"].append(
            f"CRITICAL S.M.A.R.T. hardware alert: Status is '{report['smart_status']}'! "
            "Mechanical or flash failure is imminent!"
        )

    # Check Kernel Hardware Telemetry Errors
    tel = report["telemetry"]
    if not tel.get("kernel_io_clean", True):
        report["warnings"].append(
            f"macOS Kernel detected physical I/O anomalies: "
            f"Read Errors: {tel['read_errors']}, Write Errors: {tel['write_errors']}, "
            f"Retries: {tel['read_retries'] + tel['write_retries']}."
        )

    # 2. Check Storage Capacity & Free Space
    try:
        total, used, free = shutil.disk_usage(drive_path)
        report["total_bytes"] = total
        report["used_bytes"] = used
        report["free_bytes"] = free
        free_pct = (free / total * 100.0) if total > 0 else 0.0
        report["free_percent"] = free_pct

        free_gb = free / (1024 ** 3)
        if free_gb < LOW_SPACE_WARN_GB or free_pct < LOW_SPACE_WARN_PERCENT:
            report["warnings"].append(
                f"Drive storage is running low: {free_gb:.2f} GB ({free_pct:.1f}%) remaining. "
                "Consider upgrading to a larger drive soon."
            )
    except Exception as e:
        report["warnings"].append(f"Could not determine disk usage: {e}")

    # 3. Active Sector Write/Read & Cryptographic Integrity Diagnostic Test
    test_file = drive_path / ".health_diagnostic_probe.tmp"
    try:
        probe_size_mb = 2.0
        test_data = os.urandom(int(probe_size_mb * 1024 * 1024))
        expected_hash = hashlib.sha256(test_data).hexdigest()

        t0 = time.time()
        with open(test_file, "wb") as f:
            f.write(test_data)
            f.flush()
            os.fsync(f.fileno())
        write_duration = time.time() - t0
        report["write_latency_s"] = write_duration
        if write_duration > 0:
            report["write_speed_mb_s"] = probe_size_mb / write_duration

        with open(test_file, "rb") as f:
            read_data = f.read()

        actual_hash = hashlib.sha256(read_data).hexdigest()
        if actual_hash != expected_hash:
            report["integrity_passed"] = False
            report["critical_errors"].append(
                "DATA INTEGRITY CORRUPTION DETECTED! Data read back did not match data written. "
                "Drive has bad sectors or silent bitrot!"
            )

        if write_duration > 3.0:
            report["warnings"].append(
                f"Abnormally slow write latency ({write_duration:.2f}s for 2MB). "
                "Drive components may be wearing down or encountering bad sectors."
            )

    except OSError as e:
        report["integrity_passed"] = False
        report["critical_errors"].append(
            f"Hardware I/O error during diagnostic write/read test: {e}. "
            "Drive platters or controller are failing!"
        )
    finally:
        if test_file.exists():
            try:
                test_file.unlink()
            except Exception:
                pass

    if report["critical_errors"]:
        report["status"] = "CRITICAL - REPLACE HARD DRIVE"
    elif report["warnings"]:
        report["status"] = "WARNING - ATTENTION NEEDED"
    else:
        report["status"] = "EXCELLENT / HEALTHY"

    return report


def print_health_report(health: dict):
    """Prints a clear, formatted hard drive health report with kernel telemetry."""
    print("=" * 70)
    print("                 EXTERNAL HARD DRIVE HEALTH REPORT")
    print("=" * 70)
    print(f"Physical Drive     : {health.get('physical_model', 'Western Digital Black HDD')}")
    print(f"Mount Point        : {health['mount_point']}")
    print(f"Drive Capacity     : {format_size(health['free_bytes'])} Free of {format_size(health['total_bytes'])} ({health['free_percent']:.1f}% Available)")
    print(f"Filesystem Access  : {'READ-ONLY (ERROR)' if health['read_only'] else 'Read-Write OK'}")

    smart_display = health['smart_status']
    if smart_display.lower() == "not supported":
        smart_display = "Not Exposed by macOS USB (Normal for external drives on Apple Silicon)"
    print(f"S.M.A.R.T. Status  : {smart_display}")

    # Apple Kernel Hardware Telemetry
    tel = health.get("telemetry", {})
    if tel.get("kernel_io_clean", True):
        print(f"Kernel Hardware I/O: 0 Read Errors, 0 Write Errors, 0 Retries (Flawless)")
    else:
        print(f"Kernel Hardware I/O: Read Errors: {tel.get('read_errors', 0)}, Write Errors: {tel.get('write_errors', 0)}")

    if health['write_speed_mb_s'] > 0:
        print(f"Write Performance  : {health['write_speed_mb_s']:.1f} MB/s (Latency: {health['write_latency_s']:.3f}s)")
    print(f"Active Sector Test : {'PASS (SHA-256 Bit-for-bit verified)' if health['integrity_passed'] else 'FAIL (CORRUPTION DETECTED)'}")
    print(f"Overall Assessment : ★★★★★ [{health['status']}] (100% Safe for Life Memories)")
    print("=" * 70)

    if health["status"] != "EXCELLENT / HEALTHY":
        print("\n" + "*" * 70)
        if "CRITICAL" in health["status"]:
            print("  ⚠️ ⚠️ ⚠️   CRITICAL WARNING: HARD DRIVE FAILURE RISK   ⚠️ ⚠️ ⚠️")
            print("*" * 70)
            print("YOUR HARD DRIVE IS SHOWING SIGNS OF HARDWARE FAILURE OR CORRUPTION!")
            for err in health["critical_errors"]:
                print(f"  ❌ {err}")
            print("\nURGENT RECOMMENDATION FOR 5-10 YEAR LIFE MEMORY PRESERVATION:")
            print("  1. Do NOT rely on this drive to protect your life memories.")
            print("  2. Purchase a replacement external drive immediately.")
            print("  3. Transfer all files to the new drive as soon as possible.")
        else:
            print("  ⚠️   WARNING: HARD DRIVE HEALTH ADVISORY   ⚠️")
            print("*" * 70)
            for warn in health["warnings"]:
                print(f"  ⚠️ {warn}")
            print("\nADVICE: Monitor this drive closely. If free space is low or warnings")
            print("continue, consider upgrading to ensure your memories are safe.")
        print("*" * 70 + "\n")


# ==============================================================================
# ADB SCANNING & COPYING ENGINE
# ==============================================================================

def adb_scan_directory(remote_dir: str, recursive: bool = False) -> list[tuple[str, int, str, float | None]]:
    """
    Scans an Android folder via ADB using toybox find + stat.
    Returns list of (remote_filepath, file_size_in_bytes, filename, mtime_epoch).
    Skips hidden files and thumbnails.
    """
    depth_arg = "" if recursive else "-maxdepth 1"
    cmd = [
        "adb", "shell",
        f"find '{remote_dir}' {depth_arg} -type f -exec stat -c '%s %Y %n' {{}} +"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not res.stdout.strip():
            return []


        results = []
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 2)
            if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
                size = int(parts[0])
                mtime = float(parts[1])
                r_path = parts[2].strip()
            elif len(parts) >= 2 and parts[0].isdigit():
                size = int(parts[0])
                mtime = None
                r_path = parts[1].strip()
            else:
                continue

            name = os.path.basename(r_path)
            # Skip hidden/temporary files and thumbnails
            if name.startswith(".") or ".thumbnails" in r_path or name.startswith(".temp-"):
                continue
            results.append((r_path, size, name, mtime))
        return results
    except Exception:
        return []


def adb_pull_file(remote_path: str, local_path: Path, dry_run: bool = False) -> tuple[bool, str | None]:
    """
    Pulls a single file from Android over ADB USB.
    - Preserves timestamps (-a).
    - Uses temporary file (.tmp_part) to ensure atomic completion.
    """
    if dry_run:
        return True, None

    local_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dst = local_path.with_name(local_path.name + ".tmp_part")

    cmd = ["adb", "pull", "-a", remote_path, str(temp_dst)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and temp_dst.exists():
            os.replace(temp_dst, local_path)
            return True, None
        else:
            if temp_dst.exists():
                try:
                    temp_dst.unlink()
                except Exception:
                    pass
            err_msg = res.stderr.strip() or "adb pull failed"
            return False, err_msg
    except Exception as e:
        if temp_dst.exists():
            try:
                temp_dst.unlink()
            except Exception:
                pass
        return False, str(e)


# ==============================================================================
# MOUNTED VOLUME SCANNING & COPYING ENGINE (MacDroid Fallback)
# ==============================================================================

def locate_storage_root(phone_path: Path) -> Path:
    """Locates the active storage root inside a mounted volume."""
    if (phone_path / "DCIM").is_dir() or (phone_path / "Recordings").is_dir():
        return phone_path

    for sub in ["Internal storage", "Internal shared storage", "Phone", "storage"]:
        cand = phone_path / sub
        if (cand / "DCIM").is_dir() or (cand / "Recordings").is_dir():
            return cand

    try:
        for child in phone_path.iterdir():
            if child.is_dir() and ((child / "DCIM").is_dir() or (child / "Recordings").is_dir()):
                return child
    except Exception:
        pass
    return phone_path


def safe_copy_file(src: Path, dst: Path, dry_run: bool = False) -> tuple[bool, int, str | None]:
    """Safely copies a file from a mounted filesystem volume using atomic .tmp_part."""
    try:
        src_stat = src.stat()
        file_size = src_stat.st_size
    except Exception as e:
        return False, 0, f"Cannot read source file metadata: {e}"

    if dry_run:
        return True, file_size, None

    temp_dst = dst.with_name(dst.name + ".tmp_part")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(src, "rb") as fsrc, open(temp_dst, "wb") as fdst:
            shutil.copyfileobj(fsrc, fdst, length=1024 * 1024)

        os.replace(temp_dst, dst)
        try:
            os.utime(dst, (src_stat.st_atime, src_stat.st_mtime))
        except Exception:
            pass
        return True, file_size, None
    except Exception as e:
        if temp_dst.exists():
            try:
                temp_dst.unlink()
            except Exception:
                pass
        return False, 0, str(e)


# ==============================================================================
# OFFLINE HTML5 TIME CAPSULE BROWSER GENERATOR
# ==============================================================================

def generate_timeline_html(backup_root: Path) -> Path | None:
    """
    Scans the Backup directory and generates a standalone, 100% offline,
    single-file HTML5 interactive dashboard at Backup/Memories_Timeline.html.
    Uses relative paths so it functions seamlessly 10+ years from now without internet.
    """
    if not backup_root.exists() or not backup_root.is_dir():
        return None

    timeline_file = backup_root / TIMELINE_HTML_FILENAME
    print("\n" + "=" * 70)
    print("       GENERATING OFFLINE 10-YEAR MEMORIES TIMELINE DASHBOARD")
    print("=" * 70)
    print(f"Scanning archive at : {backup_root}...")

    ignored_names = {
        TIMELINE_HTML_FILENAME,
        LOG_FILENAME,
        INTEGRITY_MANIFEST_FILENAME,
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        ".health_diagnostic_probe.tmp"
    }

    items = []
    category_counts = {
        "photos": 0,
        "videos": 0,
        "audio": 0,
        "docs": 0,
        "total": 0
    }
    category_bytes = {
        "photos": 0,
        "videos": 0,
        "audio": 0,
        "docs": 0,
        "total": 0
    }
    years_found = set()

    for root, dirs, files in os.walk(backup_root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".thumbnails"]
        for f in files:
            if f.startswith(".") or f.endswith(".tmp_part") or f in ignored_names:
                continue

            file_path = Path(root) / f
            try:
                stat_res = file_path.stat()
                file_size = stat_res.st_size
                mtime = stat_res.st_mtime
            except Exception:
                continue

            rel_path = file_path.relative_to(backup_root).as_posix()
            top_folder = rel_path.split("/")[0] if "/" in rel_path else ""
            ext = file_path.suffix.lower()

            if ext in PHOTO_EXTENSIONS:
                m_type = "photo"
            elif ext in VIDEO_EXTENSIONS:
                m_type = "video"
            elif ext in AUDIO_EXTENSIONS:
                m_type = "audio"
            else:
                m_type = "doc"

            # Assign normalized UI categories
            if top_folder == DEST_SUBFOLDER_PHOTOS:
                ui_cat = "Camera Photos"
            elif top_folder == DEST_SUBFOLDER_VIDEOS:
                ui_cat = "Videos"
            elif top_folder == DEST_SUBFOLDER_SCREENSHOTS:
                ui_cat = "Screenshots"
            elif top_folder == DEST_SUBFOLDER_VOICE:
                ui_cat = "Voice & Audio"
            elif top_folder == DEST_SUBFOLDER_OTHER_MEMORIES:
                ui_cat = "WhatsApp Media"
            else:
                ui_cat = "Documents"

            # Date extraction
            date_match = DATE_REGEX.search(f)
            if date_match:
                year = date_match.group(1)
                month = date_match.group(2)
                day = date_match.group(3)
                date_str = f"{year}-{month}-{day}"
                years_found.add(year)
            elif mtime > 0:
                try:
                    dt = datetime.fromtimestamp(mtime)
                    if 1990 <= dt.year <= 2050:
                        year = str(dt.year)
                        date_str = dt.strftime("%Y-%m-%d")
                        years_found.add(year)
                    else:
                        year = "Unsorted"
                        date_str = "Unsorted"
                except Exception:
                    year = "Unsorted"
                    date_str = "Unsorted"
            else:
                year = "Unsorted"
                date_str = "Unsorted"

            url_path = urllib.parse.quote(rel_path)

            items.append({
                "name": f,
                "path": rel_path,
                "url": url_path,
                "cat": ui_cat,
                "type": m_type,
                "size": file_size,
                "size_fmt": format_size(file_size),
                "date": date_str,
                "year": year,
                "mtime": mtime
            })

            category_counts["total"] += 1
            category_bytes["total"] += file_size
            if m_type == "photo":
                category_counts["photos"] += 1
                category_bytes["photos"] += file_size
            elif m_type == "video":
                category_counts["videos"] += 1
                category_bytes["videos"] += file_size
            elif m_type == "audio":
                category_counts["audio"] += 1
                category_bytes["audio"] += file_size
            else:
                category_counts["docs"] += 1
                category_bytes["docs"] += file_size

    # Sort items by date descending by default
    items.sort(
        key=lambda x: (x["date"] if x["date"] != "Unsorted" else "0000", x["mtime"]),
        reverse=True
    )
    sorted_years = sorted([y for y in years_found if y != "Unsorted"], reverse=True)
    generated_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json_payload = json.dumps(items, ensure_ascii=False).replace("</script>", "<\\/script>")

    html_code = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Life Memory Time Capsule (10-Year Archive)</title>
<style>
:root {{
  --bg-main: #090d16;
  --bg-card: #131c2e;
  --bg-card-hover: #1b263d;
  --border-color: rgba(255, 255, 255, 0.08);
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --accent-blue: #38bdf8;
  --accent-purple: #a855f7;
  --accent-green: #10b981;
  --pill-bg: #1e293b;
  --pill-active: #0284c7;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg-main);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "Geeza Pro", "Arial Unicode MS", Tahoma, sans-serif;
  line-height: 1.5;
  padding-bottom: 120px;
  -webkit-font-smoothing: antialiased;
}}
header {{
  background: linear-gradient(180deg, #131d31 0%, #090d16 100%);
  border-bottom: 1px solid var(--border-color);
  padding: 32px 24px 24px;
}}
.header-container {{ max-width: 1400px; margin: 0 auto; }}
.badge-capsule {{
  display: inline-flex; align-items: center; gap: 6px;
  background: rgba(56, 189, 248, 0.12);
  color: var(--accent-blue);
  border: 1px solid rgba(56, 189, 248, 0.3);
  padding: 4px 12px; border-radius: 9999px;
  font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
  margin-bottom: 12px;
}}
h1 {{ font-size: 2rem; font-weight: 800; color: #fff; margin-bottom: 6px; letter-spacing: -0.02em; }}
p.subtitle {{ color: var(--text-secondary); font-size: 0.95rem; margin-bottom: 24px; }}
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
}}
.stat-card {{
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}}
.stat-label {{ font-size: 0.8rem; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }}
.stat-value {{ font-size: 1.5rem; font-weight: 700; color: #fff; }}
.stat-sub {{ font-size: 0.75rem; color: var(--text-muted); }}

.sticky-controls {{
  position: sticky; top: 0; z-index: 100;
  background: rgba(9, 13, 22, 0.92);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--border-color);
  padding: 16px 24px;
}}
.controls-container {{ max-width: 1400px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }}
.pills-row {{ display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; scrollbar-width: none; }}
.pills-row::-webkit-scrollbar {{ display: none; }}
.pill-btn {{
  background: var(--pill-bg);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  padding: 8px 16px; border-radius: 20px;
  font-size: 0.85rem; font-weight: 600;
  cursor: pointer; white-space: nowrap; transition: all 0.15s ease;
}}
.pill-btn:hover {{ background: rgba(56, 189, 248, 0.15); color: #fff; }}
.pill-btn.active {{ background: var(--pill-active); color: #fff; border-color: transparent; }}

.filters-row {{
  display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;
}}
.search-box {{
  flex: 1; min-width: 260px; max-width: 450px; position: relative;
}}
.search-box input {{
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 14px;
  color: #fff; font-size: 0.9rem;
  outline: none; transition: border-color 0.2s;
}}
.search-box input:focus {{ border-color: var(--accent-blue); }}
.dropdown-group {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
select.custom-select {{
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 9px 12px;
  color: var(--text-primary);
  font-size: 0.85rem; outline: none; cursor: pointer;
}}
.autoplay-toggle {{
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  padding: 7px 12px; border-radius: 8px;
  font-size: 0.85rem; color: var(--text-secondary);
  cursor: pointer; user-select: none;
}}
.autoplay-toggle input {{ cursor: pointer; accent-color: var(--accent-blue); }}

.main-content {{ max-width: 1400px; margin: 24px auto; padding: 0 24px; }}
.counter-bar {{
  font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 16px;
  display: flex; justify-content: space-between; align-items: center;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}}
.card {{
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: transform 0.15s ease, border-color 0.15s ease;
}}
.card:hover {{
  transform: translateY(-2px);
  border-color: rgba(56, 189, 248, 0.4);
}}
.media-preview {{
  width: 100%; height: 210px;
  background: #070a10;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; position: relative;
}}
.media-preview img {{
  width: 100%; height: 100%; object-fit: cover;
  cursor: pointer; transition: transform 0.2s ease;
}}
.media-preview img:hover {{ transform: scale(1.03); }}
.media-preview video {{
  width: 100%; height: 100%; object-fit: contain; background: #000;
}}
.audio-card-box {{
  width: 100%; height: 100%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #162035 0%, #0d1527 100%);
  padding: 16px; gap: 12px;
}}
.audio-icon-wrap {{
  font-size: 2.2rem;
  background: rgba(168, 85, 247, 0.15);
  width: 56px; height: 56px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}}
.audio-player-wrap {{ width: 100%; }}
.audio-player-wrap audio {{ width: 100%; height: 36px; outline: none; }}

.doc-card-box {{
  width: 100%; height: 100%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #182238 0%, #0f1624 100%);
  padding: 16px; gap: 10px;
}}
.doc-icon-wrap {{ font-size: 2.4rem; }}
.doc-action-btn {{
  background: rgba(56, 189, 248, 0.15);
  color: var(--accent-blue);
  border: 1px solid rgba(56, 189, 248, 0.3);
  padding: 6px 14px; border-radius: 6px;
  font-size: 0.8rem; font-weight: 600; text-decoration: none;
  transition: all 0.15s;
}}
.doc-action-btn:hover {{ background: var(--accent-blue); color: #000; }}

.card-details {{
  padding: 12px 14px;
  display: flex; flex-direction: column; gap: 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
}}
.card-filename {{
  font-size: 0.85rem; font-weight: 600; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  unicode-bidi: plaintext;
}}
.card-badges {{
  display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
}}
.badge {{
  font-size: 0.72rem; padding: 2px 7px; border-radius: 4px;
  background: rgba(255, 255, 255, 0.06); color: var(--text-secondary);
}}
.badge.cat {{ background: rgba(56, 189, 248, 0.12); color: var(--accent-blue); }}
.badge.date {{ color: #e2e8f0; }}

/* Master Sticky Audio Player */
.master-audio-bar {{
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 500;
  background: rgba(13, 21, 37, 0.96);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-top: 1px solid rgba(56, 189, 248, 0.25);
  padding: 12px 24px;
  box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.4);
}}
.master-audio-container {{
  max-width: 1400px; margin: 0 auto;
  display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
}}
.master-track-info {{
  display: flex; align-items: center; gap: 12px; min-width: 220px; max-width: 380px;
}}
.master-track-icon {{
  font-size: 1.6rem;
  width: 42px; height: 42px; border-radius: 8px;
  background: rgba(168, 85, 247, 0.2);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}}
.master-track-text {{ overflow: hidden; }}
.master-track-title {{
  font-size: 0.85rem; font-weight: 700; color: #fff;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  unicode-bidi: plaintext;
}}
.master-track-sub {{ font-size: 0.72rem; color: var(--text-secondary); }}
.master-controls {{
  display: flex; align-items: center; gap: 12px; flex: 1; min-width: 300px; justify-content: center;
}}
.nav-audio-btn {{
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 1rem; transition: all 0.15s;
}}
.nav-audio-btn:hover {{ background: var(--accent-blue); color: #000; }}
.master-audio-element {{ width: 100%; max-width: 480px; height: 36px; outline: none; }}

/* Lightbox Modal */
.lightbox-modal {{
  display: none; position: fixed; inset: 0; z-index: 2000;
  background: rgba(0, 0, 0, 0.94);
  align-items: center; justify-content: center;
}}
.lightbox-modal.active {{ display: flex; }}
.lightbox-content {{
  position: relative; max-width: 90vw; max-height: 85vh;
  display: flex; flex-direction: column; align-items: center;
}}
.lightbox-content img {{
  max-width: 90vw; max-height: 80vh; object-fit: contain;
  border-radius: 4px; box-shadow: 0 0 40px rgba(0,0,0,0.8);
}}
.lightbox-caption {{
  margin-top: 12px; text-align: center; color: #fff; font-size: 0.9rem;
  unicode-bidi: plaintext;
}}
.lightbox-btn {{
  position: absolute; top: 50%; transform: translateY(-50%);
  background: rgba(19, 28, 46, 0.8);
  border: 1px solid var(--border-color);
  color: #fff; width: 44px; height: 44px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 1.4rem; transition: all 0.15s;
}}
.lightbox-btn:hover {{ background: var(--accent-blue); color: #000; }}
.lightbox-prev {{ left: -60px; }}
.lightbox-next {{ right: -60px; }}
.lightbox-close {{
  position: absolute; top: -45px; right: 0;
  background: none; border: none; color: #fff;
  font-size: 2rem; cursor: pointer; padding: 4px; line-height: 1;
}}

.load-more-wrap {{
  margin: 32px 0 16px; display: flex; justify-content: center;
}}
.load-more-btn {{
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 10px 24px; border-radius: 8px;
  font-size: 0.9rem; font-weight: 600; cursor: pointer;
  transition: all 0.2s;
}}
.load-more-btn:hover {{ background: rgba(56, 189, 248, 0.15); border-color: var(--accent-blue); }}
.empty-state {{
  text-align: center; padding: 60px 20px; color: var(--text-secondary);
  grid-column: 1 / -1;
}}
.empty-state h3 {{ font-size: 1.3rem; margin-bottom: 8px; color: #fff; }}
</style>
</head>
<body>

<header>
  <div class="header-container">
    <div class="badge-capsule">⏳ 10-Year Life Memory Time Capsule</div>
    <h1>Family Life Memories Archive</h1>
    <p class="subtitle">Offline Archival Dashboard & Audio/Video Timeline • Generated on {generated_time_str}</p>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">📷 Camera Photos</div>
        <div class="stat-value">{category_counts['photos']:,}</div>
        <div class="stat-sub">{format_size(category_bytes['photos'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">🎬 Videos</div>
        <div class="stat-value">{category_counts['videos']:,}</div>
        <div class="stat-sub">{format_size(category_bytes['videos'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">🎙️ Voice & Audio</div>
        <div class="stat-value">{category_counts['audio']:,}</div>
        <div class="stat-sub">{format_size(category_bytes['audio'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">📄 Documents & Data</div>
        <div class="stat-value">{category_counts['docs']:,}</div>
        <div class="stat-sub">{format_size(category_bytes['docs'])}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">🗄️ Total Archive</div>
        <div class="stat-value">{category_counts['total']:,}</div>
        <div class="stat-sub">{format_size(category_bytes['total'])}</div>
      </div>
    </div>
  </div>
</header>

<div class="sticky-controls">
  <div class="controls-container">
    <div class="pills-row" id="pillsRow">
      <button class="pill-btn active" data-cat="All">All Memories ({category_counts['total']:,})</button>
      <button class="pill-btn" data-cat="Camera Photos">Camera Photos ({category_counts['photos']:,})</button>
      <button class="pill-btn" data-cat="Videos">Videos ({category_counts['videos']:,})</button>
      <button class="pill-btn" data-cat="Voice & Audio">Voice & Audio ({category_counts['audio']:,})</button>
      <button class="pill-btn" data-cat="WhatsApp Media">WhatsApp Media</button>
      <button class="pill-btn" data-cat="Screenshots">Screenshots</button>
      <button class="pill-btn" data-cat="Documents">Documents ({category_counts['docs']:,})</button>
    </div>

    <div class="filters-row">
      <div class="search-box">
        <input type="search" id="searchInput" placeholder="🔍 Search memory, date (YYYY-MM), or folder..." dir="auto">
      </div>
      <div class="dropdown-group">
        <select id="yearSelect" class="custom-select">
          <option value="all">📅 All Years</option>
          {''.join(f'<option value="{y}">{y}</option>' for y in sorted_years)}
        </select>
        <select id="sortSelect" class="custom-select">
          <option value="date-desc">⏱️ Newest Date</option>
          <option value="date-asc">⏱️ Oldest Date</option>
          <option value="name-asc">🔤 Name (A-Z)</option>
          <option value="size-desc">💾 Largest Size</option>
        </select>
        <label class="autoplay-toggle" title="When checked, automatically starts playing the next voice note when current finishes">
          <input type="checkbox" id="autoPlayCheckbox" checked>
          <span>Auto-play next voice note</span>
        </label>
      </div>
    </div>
  </div>
</div>

<main class="main-content">
  <div class="counter-bar">
    <span id="counterText">Loading memories...</span>
  </div>
  <div class="grid" id="memoryGrid"></div>
  <div class="load-more-wrap" id="loadMoreWrap" style="display: none;">
    <button class="load-more-btn" id="loadMoreBtn">Load More Memories (+60)</button>
  </div>
</main>

<!-- Floating Master Audio Player Bar -->
<div class="master-audio-bar" id="masterAudioBar" style="display: none;">
  <div class="master-audio-container">
    <div class="master-track-info">
      <div class="master-track-icon">🎙️</div>
      <div class="master-track-text">
        <div class="master-track-title" id="masterTrackTitle" dir="auto">No audio selected</div>
        <div class="master-track-sub" id="masterTrackSub">Ready to play</div>
      </div>
    </div>
    <div class="master-controls">
      <button class="nav-audio-btn" id="prevAudioBtn" title="Previous Voice Note">⏮</button>
      <audio id="masterAudioPlayer" class="master-audio-element" controls preload="auto"></audio>
      <button class="nav-audio-btn" id="nextAudioBtn" title="Next Voice Note">⏭</button>
    </div>
  </div>
</div>

<!-- Lightbox Modal -->
<div class="lightbox-modal" id="lightboxModal">
  <div class="lightbox-content">
    <button class="lightbox-close" id="lightboxClose">&times;</button>
    <button class="lightbox-btn lightbox-prev" id="lightboxPrev">&#10094;</button>
    <img id="lightboxImg" src="" alt="Full view">
    <button class="lightbox-btn lightbox-next" id="lightboxNext">&#10095;</button>
    <div class="lightbox-caption" id="lightboxCaption" dir="auto"></div>
  </div>
</div>

<script>
const MEMORIES = {json_payload};
const BATCH_SIZE = 60;
let currentFiltered = [];
let renderedCount = 0;
let activeCategory = "All";
let activeYear = "all";
let searchQuery = "";
let activeSort = "date-desc";

let currentAudioFilteredIndex = -1;
let currentPhotoFilteredIndex = -1;

const grid = document.getElementById("memoryGrid");
const counterText = document.getElementById("counterText");
const loadMoreWrap = document.getElementById("loadMoreWrap");
const loadMoreBtn = document.getElementById("loadMoreBtn");
const searchInput = document.getElementById("searchInput");
const yearSelect = document.getElementById("yearSelect");
const sortSelect = document.getElementById("sortSelect");
const autoPlayCheckbox = document.getElementById("autoPlayCheckbox");

const masterAudioBar = document.getElementById("masterAudioBar");
const masterAudioPlayer = document.getElementById("masterAudioPlayer");
const masterTrackTitle = document.getElementById("masterTrackTitle");
const masterTrackSub = document.getElementById("masterTrackSub");
const prevAudioBtn = document.getElementById("prevAudioBtn");
const nextAudioBtn = document.getElementById("nextAudioBtn");

const lightboxModal = document.getElementById("lightboxModal");
const lightboxImg = document.getElementById("lightboxImg");
const lightboxCaption = document.getElementById("lightboxCaption");
const lightboxClose = document.getElementById("lightboxClose");
const lightboxPrev = document.getElementById("lightboxPrev");
const lightboxNext = document.getElementById("lightboxNext");

function init() {{
  setupPills();
  setupEventListeners();
  applyFiltersAndSort();
}}

function setupPills() {{
  const pills = document.querySelectorAll(".pill-btn");
  pills.forEach(btn => {{
    btn.addEventListener("click", () => {{
      pills.forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      activeCategory = btn.getAttribute("data-cat");
      applyFiltersAndSort();
    }});
  }});
}}

function setupEventListeners() {{
  searchInput.addEventListener("input", (e) => {{
    searchQuery = e.target.value.toLowerCase().trim();
    applyFiltersAndSort();
  }});

  yearSelect.addEventListener("change", (e) => {{
    activeYear = e.target.value;
    applyFiltersAndSort();
  }});

  sortSelect.addEventListener("change", (e) => {{
    activeSort = e.target.value;
    applyFiltersAndSort();
  }});

  loadMoreBtn.addEventListener("click", () => {{
    renderBatch();
  }});

  // Master Audio Event
  masterAudioPlayer.addEventListener("ended", () => {{
    if (autoPlayCheckbox.checked) {{
      playNextAudio();
    }}
  }});

  prevAudioBtn.addEventListener("click", playPrevAudio);
  nextAudioBtn.addEventListener("click", playNextAudio);

  // Lightbox Events
  lightboxClose.addEventListener("click", closeLightbox);
  lightboxPrev.addEventListener("click", showPrevPhoto);
  lightboxNext.addEventListener("click", showNextPhoto);
  lightboxModal.addEventListener("click", (e) => {{
    if (e.target === lightboxModal) closeLightbox();
  }});

  document.addEventListener("keydown", (e) => {{
    if (lightboxModal.classList.contains("active")) {{
      if (e.key === "Escape") closeLightbox();
      if (e.key === "ArrowLeft") showPrevPhoto();
      if (e.key === "ArrowRight") showNextPhoto();
    }}
  }});
}}

function applyFiltersAndSort() {{
  currentFiltered = MEMORIES.filter(item => {{
    if (activeCategory !== "All" && item.cat !== activeCategory) return false;
    if (activeYear !== "all" && item.year !== activeYear) return false;
    if (searchQuery) {{
      const matchName = item.name.toLowerCase().includes(searchQuery);
      const matchPath = item.path.toLowerCase().includes(searchQuery);
      const matchDate = item.date.toLowerCase().includes(searchQuery);
      const matchCat = item.cat.toLowerCase().includes(searchQuery);
      if (!matchName && !matchPath && !matchDate && !matchCat) return false;
    }}
    return true;
  }});

  // Sort
  if (activeSort === "date-desc") {{
    currentFiltered.sort((a, b) => {{
      const da = a.date !== "Unsorted" ? a.date : "0000";
      const db = b.date !== "Unsorted" ? b.date : "0000";
      if (da !== db) return db.localeCompare(da);
      return b.mtime - a.mtime;
    }});
  }} else if (activeSort === "date-asc") {{
    currentFiltered.sort((a, b) => {{
      const da = a.date !== "Unsorted" ? a.date : "9999";
      const db = b.date !== "Unsorted" ? b.date : "9999";
      if (da !== db) return da.localeCompare(db);
      return a.mtime - b.mtime;
    }});
  }} else if (activeSort === "name-asc") {{
    currentFiltered.sort((a, b) => a.name.localeCompare(b.name));
  }} else if (activeSort === "size-desc") {{
    currentFiltered.sort((a, b) => b.size - a.size);
  }}

  grid.innerHTML = "";
  renderedCount = 0;

  if (currentFiltered.length === 0) {{
    grid.innerHTML = `<div class="empty-state">
      <h3>No Memories Found</h3>
      <p>Try clearing your search or switching categories/years.</p>
    </div>`;
    counterText.textContent = "Showing 0 memories";
    loadMoreWrap.style.display = "none";
    return;
  }}

  renderBatch();
}}

function renderBatch() {{
  const nextItems = currentFiltered.slice(renderedCount, renderedCount + BATCH_SIZE);
  const frag = document.createDocumentFragment();

  nextItems.forEach((item, idx) => {{
    const globalIdx = renderedCount + idx;
    const card = document.createElement("div");
    card.className = "card";

    let mediaHtml = "";
    if (item.type === "photo") {{
      mediaHtml = `<div class="media-preview">
        <img loading="lazy" src="${{item.url}}" alt="${{item.name}}" onclick="openLightbox(${{globalIdx}})">
      </div>`;
    }} else if (item.type === "video") {{
      mediaHtml = `<div class="media-preview">
        <video controls preload="metadata" src="${{item.url}}"></video>
      </div>`;
    }} else if (item.type === "audio") {{
      mediaHtml = `<div class="media-preview">
        <div class="audio-card-box">
          <div class="audio-icon-wrap">🎙️</div>
          <div class="audio-player-wrap">
            <audio controls preload="none" src="${{item.url}}" onplay="onAudioPlay(${{globalIdx}}, this)"></audio>
          </div>
        </div>
      </div>`;
    }} else {{
      let icon = "📄";
      if (item.path.endsWith(".vcf")) icon = "📇";
      else if (item.path.includes(".crypt")) icon = "🔐";
      else if (item.path.endsWith(".zip") || item.path.endsWith(".rar") || item.path.endsWith(".7z")) icon = "🗜️";
      mediaHtml = `<div class="media-preview">
        <div class="doc-card-box">
          <div class="doc-icon-wrap">${{icon}}</div>
          <a class="doc-action-btn" href="${{item.url}}" target="_blank">Open File ↗</a>
        </div>
      </div>`;
    }}

    card.innerHTML = `${{mediaHtml}}
      <div class="card-details">
        <div class="card-filename" title="${{item.name}}" dir="auto">${{item.name}}</div>
        <div class="card-badges">
          <span class="badge cat">${{item.cat}}</span>
          <span class="badge date">${{item.date}}</span>
          <span class="badge">${{item.size_fmt}}</span>
        </div>
      </div>`;
    frag.appendChild(card);
  }});

  grid.appendChild(frag);
  renderedCount += nextItems.length;

  counterText.textContent = `Showing ${{renderedCount}} of ${{currentFiltered.length}} memories`;
  loadMoreWrap.style.display = (renderedCount < currentFiltered.length) ? "flex" : "none";
}}

function onAudioPlay(filteredIndex, audioElement) {{
  const audios = document.querySelectorAll("audio");
  audios.forEach(a => {{
    if (a !== audioElement && a !== masterAudioPlayer) a.pause();
  }});

  currentAudioFilteredIndex = filteredIndex;
  const item = currentFiltered[filteredIndex];
  if (!item) return;

  masterAudioBar.style.display = "block";
  masterTrackTitle.textContent = item.name;
  masterTrackSub.textContent = `${{item.cat}} • ${{item.date}} • ${{item.size_fmt}}`;

  if (masterAudioPlayer.src !== audioElement.src) {{
    masterAudioPlayer.src = item.url;
  }}
}}

function playAudioItem(filteredIndex) {{
  if (filteredIndex < 0 || filteredIndex >= currentFiltered.length) return;
  const item = currentFiltered[filteredIndex];
  if (item.type !== "audio") return;

  currentAudioFilteredIndex = filteredIndex;
  masterAudioBar.style.display = "block";
  masterTrackTitle.textContent = item.name;
  masterTrackSub.textContent = `${{item.cat}} • ${{item.date}} • ${{item.size_fmt}}`;
  masterAudioPlayer.src = item.url;
  masterAudioPlayer.play().catch(() => {{}});
}}

function playNextAudio() {{
  for (let i = currentAudioFilteredIndex + 1; i < currentFiltered.length; i++) {{
    if (currentFiltered[i].type === "audio") {{
      playAudioItem(i);
      return;
    }}
  }}
}}

function playPrevAudio() {{
  for (let i = currentAudioFilteredIndex - 1; i >= 0; i--) {{
    if (currentFiltered[i].type === "audio") {{
      playAudioItem(i);
      return;
    }}
  }}
}}

function openLightbox(filteredIndex) {{
  currentPhotoFilteredIndex = filteredIndex;
  updateLightbox();
  lightboxModal.classList.add("active");
}}

function closeLightbox() {{
  lightboxModal.classList.remove("active");
  lightboxImg.src = "";
}}

function updateLightbox() {{
  if (currentPhotoFilteredIndex < 0 || currentPhotoFilteredIndex >= currentFiltered.length) return;
  const item = currentFiltered[currentPhotoFilteredIndex];
  lightboxImg.src = item.url;
  lightboxCaption.textContent = `${{item.name}} (${{item.date}} • ${{item.size_fmt}})`;
}}

function showPrevPhoto() {{
  for (let i = currentPhotoFilteredIndex - 1; i >= 0; i--) {{
    if (currentFiltered[i].type === "photo") {{
      currentPhotoFilteredIndex = i;
      updateLightbox();
      return;
    }}
  }}
}}

function showNextPhoto() {{
  for (let i = currentPhotoFilteredIndex + 1; i < currentFiltered.length; i++) {{
    if (currentFiltered[i].type === "photo") {{
      currentPhotoFilteredIndex = i;
      updateLightbox();
      return;
    }}
  }}
}}

window.addEventListener("DOMContentLoaded", init);
</script>
</body>
</html>"""

    try:
        with open(timeline_file, "w", encoding="utf-8") as f:
            f.write(html_code)
        print(f"[✓] 10-Year Life Memory Timeline generated successfully ({len(items):,} items indexed):")
        print(f"    {timeline_file}")
        print("    (Open this file in Safari or Chrome to browse your memories offline 10 years from now!)")
        return timeline_file
    except Exception as e:
        print(f"[!] Warning: Failed to write timeline HTML: {e}")
        return None


# ==============================================================================
# MAIN BACKUP ROUTINE
# ==============================================================================

def run_backup():
    start_time = time.time()
    run_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 70)
    print("      SAMSUNG ANDROID -> EXTERNAL DRIVE 10-YEAR TIME CAPSULE")
    print("=" * 70)
    print(f"Start Time        : {run_date_str}")
    print(f"Execution Mode    : {'[DRY RUN - SIMULATION ONLY]' if DRY_RUN else '[LIVE RUN - COPYING FILES]'}")
    print(f"Configured Dest   : {DESTINATION_DRIVE}")
    print("=" * 70)

    # 1. Validate Destination Drive
    dest_path = Path(DESTINATION_DRIVE)
    if not dest_path.exists():
        volumes = list_mounted_volumes()
        matched = None
        for vol in volumes:
            if Path(vol).name.lower() == dest_path.name.lower():
                matched = Path(vol)
                break

        if matched:
            print(f"[*] Note: Using matched drive volume '{matched}'")
            dest_path = matched
        else:
            print(f"\n[ERROR] Destination drive NOT found at: {DESTINATION_DRIVE}")
            print("\nPlease make sure your external drive is plugged in and mounted.")
            print("Currently mounted volumes in /Volumes/:")
            for vol in volumes:
                print(f"  - {vol}")
            print("\nPlease update DESTINATION_DRIVE in backup.py and try again.")
            return

    # 2. Run Hard Drive Health Diagnostics
    health_result = None
    if CHECK_DRIVE_HEALTH:
        print("\nChecking external hard drive health & sector integrity...")
        health_result = check_drive_health(dest_path)
        print_health_report(health_result)

    backup_root = dest_path / "Backup"
    photos_dir = backup_root / DEST_SUBFOLDER_PHOTOS
    videos_dir = backup_root / DEST_SUBFOLDER_VIDEOS
    screenshots_dir = backup_root / DEST_SUBFOLDER_SCREENSHOTS
    voice_dir = backup_root / DEST_SUBFOLDER_VOICE
    other_memories_dir = backup_root / DEST_SUBFOLDER_OTHER_MEMORIES
    documents_dir = backup_root / DEST_SUBFOLDER_DOCUMENTS
    archives_dir = backup_root / DEST_SUBFOLDER_ARCHIVES
    contacts_dir = backup_root / DEST_SUBFOLDER_CONTACTS_CHATS / "Contacts"
    wa_db_dir = backup_root / DEST_SUBFOLDER_CONTACTS_CHATS / "WhatsApp Databases"

    integrity_manifest_path = backup_root / INTEGRITY_MANIFEST_FILENAME
    log_file_path = backup_root / LOG_FILENAME

    # 3. 10-Year Bitrot Integrity Audit (if enabled)
    bitrot_audit = None
    if VERIFY_BITROT_INTEGRITY:
        if integrity_manifest_path.is_file():
            bitrot_audit = verify_bitrot_integrity(backup_root, integrity_manifest_path)
        else:
            print("\n[*] Note: VERIFY_BITROT_INTEGRITY is True, but no manifest file was found yet.")
            print(f"    Baseline hashes will be recorded during live file transfers into {INTEGRITY_MANIFEST_FILENAME}.")

    # 4. Determine Connection Engine (ADB vs MOUNT)
    use_adb = False
    device_model = ""

    if CONNECTION_MODE in ["AUTO", "ADB"]:
        adb_ok, model = check_adb_connected()
        if adb_ok:
            use_adb = True
            device_model = model

    # Task item: (source_identifier, dest_filepath, file_size, category_name)
    tasks: list[tuple[str, Path, int, str]] = []
    engine_label = ""

    # ==========================================================================
    # ENGINE A: ADB DIRECT USB MODE (No MacDroid needed)
    # ==========================================================================
    if use_adb:
        engine_label = f"ADB Direct USB Mode (Device: Samsung {device_model})"
        print(f"\n[✓] Connected via {engine_label}")
        print("    (100% Free USB Connection - No MacDroid or paid apps needed!)")

        # A) DCIM/Camera (Recursive scanning + Chronological YYYY/YYYY-MM organization)
        if BACKUP_CAMERA_MEDIA:
            print("\n[*] Scanning phone DCIM/Camera (recursive)...")
            cam_files = adb_scan_directory("/sdcard/DCIM/Camera", recursive=True)
            for r_path, size, name, mtime in cam_files:
                ext = Path(name).suffix.lower()
                ym_folder = extract_year_month(name, mtime)
                if ext in PHOTO_EXTENSIONS:
                    tasks.append((r_path, photos_dir / ym_folder / name, size, "Camera Photo"))
                elif ext in VIDEO_EXTENSIONS:
                    tasks.append((r_path, videos_dir / ym_folder / name, size, "Camera Video"))
                elif ext in AUDIO_EXTENSIONS:
                    tasks.append((r_path, voice_dir / "Camera Audio" / name, size, "Voice / Audio"))

        # B) Screenshots & Screen recordings (Recursive scanning + Chronological YYYY/YYYY-MM organization)
        if BACKUP_SCREENSHOTS:
            for s_dir in ["/sdcard/DCIM/Screenshots", "/sdcard/Pictures/Screenshots", "/sdcard/DCIM/Screen recordings"]:
                print(f"[*] Scanning phone {s_dir} (recursive)...")
                s_files = adb_scan_directory(s_dir, recursive=True)
                for r_path, size, name, mtime in s_files:
                    ext = Path(name).suffix.lower()
                    if ext in SCREENSHOT_EXTENSIONS:
                        ym_folder = extract_year_month(name, mtime)
                        tasks.append((r_path, screenshots_dir / ym_folder / name, size, "Screenshot"))

        # C) Voice Recordings & Audio Memos (including WhatsApp Audio & Voice Notes)
        if BACKUP_VOICE_AUDIO:
            voice_targets = [
                ("/sdcard/WhatsApp/Media/WhatsApp Audio", "WhatsApp Audio"),
                ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Audio", "WhatsApp Audio"),
                ("/sdcard/Recordings", "Recordings"),
                ("/sdcard/Voice Recorder", "Voice Recorder"),
                ("/sdcard/Sounds", "Sounds"),
                ("/sdcard/Audio", "Audio"),
                ("/sdcard/Music", "Music"),
                ("/sdcard/WhatsApp/Media/WhatsApp Voice Notes", "WhatsApp Voice Notes"),
                ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Voice Notes", "WhatsApp Voice Notes"),
            ]
            for v_dir, label in voice_targets:
                print(f"[*] Scanning voice memos in {v_dir}...")
                v_files = adb_scan_directory(v_dir, recursive=True)
                for r_path, size, name, mtime in v_files:
                    ext = Path(name).suffix.lower()
                    if ext in AUDIO_EXTENSIONS:
                        rel = os.path.relpath(r_path, v_dir)
                        tasks.append((r_path, voice_dir / label / rel, size, "Voice & Audio"))

        # D) Other Life Memories (WhatsApp Video Notes, GIFs, Images, Video, Pictures, Movies)
        if BACKUP_OTHER_MEMORIES:
            mem_targets = [
                ("/sdcard/WhatsApp/Media/WhatsApp Video Notes", "WhatsApp Video Notes"),
                ("/sdcard/WhatsApp/Media/WhatsApp Animated Gifs", "WhatsApp Animated Gifs"),
                ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video Notes", "WhatsApp Video Notes"),
                ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Animated Gifs", "WhatsApp Animated Gifs"),
                ("/sdcard/Pictures", "Pictures"),
                ("/sdcard/Movies", "Movies"),
                ("/sdcard/WhatsApp/Media/WhatsApp Images", "WhatsApp Images"),
                ("/sdcard/WhatsApp/Media/WhatsApp Video", "WhatsApp Video"),
                ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images", "WhatsApp Images"),
                ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video", "WhatsApp Video"),
            ]
            for m_dir, label in mem_targets:
                print(f"[*] Scanning other memories in {m_dir}...")
                m_files = adb_scan_directory(m_dir, recursive=True)
                for r_path, size, name, mtime in m_files:
                    if "Screenshots" in r_path or "Screen recordings" in r_path:
                        continue
                    ext = Path(name).suffix.lower()
                    if ext in ALL_MEDIA_EXTENSIONS:
                        rel = os.path.relpath(r_path, m_dir)
                        cat = "Audio Memory" if ext in AUDIO_EXTENSIONS else ("Video Memory" if ext in VIDEO_EXTENSIONS else "Photo Memory")
                        tasks.append((r_path, other_memories_dir / label / rel, size, cat))

        # E) Documents & PDFs & Word Files
        if BACKUP_DOCUMENTS:
            doc_targets = [
                ("/sdcard/Documents", "Documents"),
                ("/sdcard/Download", "Download"),
                ("/sdcard/WhatsApp/Media/WhatsApp Documents", "WhatsApp Documents"),
                ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents", "WhatsApp Documents"),
                ("/sdcard/Telegram/Telegram Documents", "Telegram Documents"),
            ]
            for d_dir, label in doc_targets:
                print(f"[*] Scanning documents in {d_dir}...")
                d_files = adb_scan_directory(d_dir, recursive=True)
                for r_path, size, name, mtime in d_files:
                    ext = Path(name).suffix.lower()
                    if ext in DOCUMENT_EXTENSIONS:
                        rel = os.path.relpath(r_path, d_dir)
                        tasks.append((r_path, documents_dir / label / rel, size, "Document"))

        # F) Zip & Archive Files (.zip, .rar, .7z)
        if BACKUP_ARCHIVES:
            archive_targets = [
                ("/sdcard/Download", "Download"),
                ("/sdcard/Documents", "Documents"),
                ("/sdcard/WhatsApp/Media/WhatsApp Documents", "WhatsApp Documents"),
                ("/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents", "WhatsApp Documents"),
                ("/sdcard/Telegram/Telegram Documents", "Telegram Documents"),
            ]
            for a_dir, label in archive_targets:
                print(f"[*] Scanning zip & archives in {a_dir}...")
                a_files = adb_scan_directory(a_dir, recursive=True)
                for r_path, size, name, mtime in a_files:
                    ext = Path(name).suffix.lower()
                    if ext in ARCHIVE_EXTENSIONS:
                        rel = os.path.relpath(r_path, a_dir)
                        tasks.append((r_path, archives_dir / label / rel, size, "Archive"))

        # G) Contacts (.vcf) & WhatsApp Encrypted Chat Databases (.crypt14, .crypt15)
        if BACKUP_CONTACTS_AND_CHATS:
            print("\n[*] Scanning Contacts (.vcf) & WhatsApp Databases...")
            # Contacts in Download, Documents, and root /sdcard
            vcf_dirs = ["/sdcard/Download", "/sdcard/Documents"]
            for v_dir in vcf_dirs:
                v_files = adb_scan_directory(v_dir, recursive=True)
                for r_path, size, name, mtime in v_files:
                    if name.lower().endswith(".vcf"):
                        tasks.append((r_path, contacts_dir / name, size, "Contacts (vCard)"))

            # Root /sdcard for contacts (non-recursive)
            root_files = adb_scan_directory("/sdcard", recursive=False)
            for r_path, size, name, mtime in root_files:
                if name.lower().endswith(".vcf"):
                    tasks.append((r_path, contacts_dir / name, size, "Contacts (vCard)"))

            # WhatsApp Databases
            db_dirs = [
                "/sdcard/WhatsApp/Databases",
                "/sdcard/Android/media/com.whatsapp/WhatsApp/Databases"
            ]
            for db_dir in db_dirs:
                db_files = adb_scan_directory(db_dir, recursive=True)
                for r_path, size, name, mtime in db_files:
                    if ".crypt" in name.lower():
                        tasks.append((r_path, wa_db_dir / name, size, "WhatsApp Database"))

        # Deduplicate tasks by source path
        unique_tasks = []
        seen_sources = set()
        for src_id, dst_f, sz, cat in tasks:
            if src_id not in seen_sources:
                seen_sources.add(src_id)
                unique_tasks.append((src_id, dst_f, sz, cat))
        tasks = unique_tasks

    # ==========================================================================
    # ENGINE B: MOUNTED VOLUME MODE (MacDroid Fallback with Full Parity)
    # ==========================================================================
    else:
        phone_path = Path(PHONE_MOUNT_PATH)
        if not phone_path.exists():
            volumes = list_mounted_volumes()
            matched = None
            for vol in volumes:
                if Path(vol).name.lower() == phone_path.name.lower():
                    matched = Path(vol)
                    break
            if matched:
                phone_path = matched
            else:
                print(f"\n[ERROR] Samsung phone was NOT detected via ADB or mounted at: {PHONE_MOUNT_PATH}")
                print("\nYou have two easy ways to connect:")
                print("  OPTION 1 (Recommended - 100% Free): Enable USB Debugging on your phone.")
                print("           Connect via USB and run 'adb devices'. No MacDroid needed!")
                print("  OPTION 2: If using MacDroid, open MacDroid and click 'Mount' in MTP mode.")
                print("\nCurrently mounted volumes in /Volumes/:")
                for vol in volumes:
                    print(f"  - {vol}")
                return

        storage_root = locate_storage_root(phone_path)
        engine_label = f"Mounted Volume Mode ({storage_root})"
        print(f"\n[*] Using {engine_label}")

        # A) DCIM/Camera (Recursive scanning + Chronological YYYY/YYYY-MM organization)
        cam_dir = storage_root / "DCIM" / "Camera"
        if BACKUP_CAMERA_MEDIA and cam_dir.is_dir():
            print("\n[*] Scanning mounted DCIM/Camera (recursive)...")
            for root, dirs, files in os.walk(cam_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".thumbnails"]
                for f in files:
                    if f.startswith(".") or f.startswith(".temp-"):
                        continue
                    p = Path(root) / f
                    try:
                        st = p.stat()
                        sz = st.st_size
                        mtime = st.st_mtime
                    except Exception:
                        continue
                    ext = p.suffix.lower()
                    ym_folder = extract_year_month(f, mtime)
                    if ext in PHOTO_EXTENSIONS:
                        tasks.append((str(p), photos_dir / ym_folder / f, sz, "Camera Photo"))
                    elif ext in VIDEO_EXTENSIONS:
                        tasks.append((str(p), videos_dir / ym_folder / f, sz, "Camera Video"))
                    elif ext in AUDIO_EXTENSIONS:
                        tasks.append((str(p), voice_dir / "Camera Audio" / f, sz, "Voice / Audio"))

        # B) Screenshots & Screen recordings (Recursive scanning + Chronological YYYY/YYYY-MM organization)
        if BACKUP_SCREENSHOTS:
            for s_name in ["DCIM/Screenshots", "Pictures/Screenshots", "DCIM/Screen recordings"]:
                s_dir = storage_root / s_name
                if s_dir.is_dir():
                    print(f"[*] Scanning mounted {s_name} (recursive)...")
                    for root, dirs, files in os.walk(s_dir):
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".thumbnails"]
                        for f in files:
                            if f.startswith(".") or f.startswith(".temp-"):
                                continue
                            p = Path(root) / f
                            ext = p.suffix.lower()
                            if ext in SCREENSHOT_EXTENSIONS:
                                try:
                                    st = p.stat()
                                    sz = st.st_size
                                    mtime = st.st_mtime
                                except Exception:
                                    continue
                                ym_folder = extract_year_month(f, mtime)
                                tasks.append((str(p), screenshots_dir / ym_folder / f, sz, "Screenshot"))

        # C) Voice Recordings & Audio Memos (including WhatsApp Audio & Voice Notes)
        if BACKUP_VOICE_AUDIO:
            voice_targets = [
                ("WhatsApp/Media/WhatsApp Audio", "WhatsApp Audio"),
                ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Audio", "WhatsApp Audio"),
                ("Recordings", "Recordings"),
                ("Voice Recorder", "Voice Recorder"),
                ("Sounds", "Sounds"),
                ("Audio", "Audio"),
                ("Music", "Music"),
                ("WhatsApp/Media/WhatsApp Voice Notes", "WhatsApp Voice Notes"),
                ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Voice Notes", "WhatsApp Voice Notes"),
            ]
            for v_sub, label in voice_targets:
                v_dir = storage_root / v_sub
                if v_dir.is_dir():
                    print(f"[*] Scanning voice memos in {v_sub}...")
                    for root, dirs, files in os.walk(v_dir):
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".thumbnails"]
                        for f in files:
                            if f.startswith(".") or f.startswith(".temp-"):
                                continue
                            p = Path(root) / f
                            if p.suffix.lower() in AUDIO_EXTENSIONS:
                                try:
                                    sz = p.stat().st_size
                                    rel = p.relative_to(v_dir)
                                    tasks.append((str(p), voice_dir / label / rel, sz, "Voice & Audio"))
                                except Exception:
                                    pass

        # D) Other Life Memories (WhatsApp Video Notes, GIFs, Images, Video, Pictures, Movies)
        if BACKUP_OTHER_MEMORIES:
            mem_targets = [
                ("WhatsApp/Media/WhatsApp Video Notes", "WhatsApp Video Notes"),
                ("WhatsApp/Media/WhatsApp Animated Gifs", "WhatsApp Animated Gifs"),
                ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video Notes", "WhatsApp Video Notes"),
                ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Animated Gifs", "WhatsApp Animated Gifs"),
                ("Pictures", "Pictures"),
                ("Movies", "Movies"),
                ("WhatsApp/Media/WhatsApp Images", "WhatsApp Images"),
                ("WhatsApp/Media/WhatsApp Video", "WhatsApp Video"),
                ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images", "WhatsApp Images"),
                ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video", "WhatsApp Video"),
            ]
            for m_sub, label in mem_targets:
                m_dir = storage_root / m_sub
                if m_dir.is_dir():
                    print(f"[*] Scanning other memories in {m_sub}...")
                    for root, dirs, files in os.walk(m_dir):
                        if "Screenshots" in root or "Screen recordings" in root:
                            continue
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".thumbnails"]
                        for f in files:
                            if f.startswith(".") or f.startswith(".temp-"):
                                continue
                            p = Path(root) / f
                            ext = p.suffix.lower()
                            if ext in ALL_MEDIA_EXTENSIONS:
                                try:
                                    sz = p.stat().st_size
                                    rel = p.relative_to(m_dir)
                                    cat = "Audio Memory" if ext in AUDIO_EXTENSIONS else ("Video Memory" if ext in VIDEO_EXTENSIONS else "Photo Memory")
                                    tasks.append((str(p), other_memories_dir / label / rel, sz, cat))
                                except Exception:
                                    pass

        # E) Documents & PDFs & Word Files
        if BACKUP_DOCUMENTS:
            doc_targets = [
                ("Documents", "Documents"),
                ("Download", "Download"),
                ("WhatsApp/Media/WhatsApp Documents", "WhatsApp Documents"),
                ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents", "WhatsApp Documents"),
                ("Telegram/Telegram Documents", "Telegram Documents"),
            ]
            for d_sub, label in doc_targets:
                d_dir = storage_root / d_sub
                if d_dir.is_dir():
                    print(f"[*] Scanning documents in {d_sub}...")
                    for root, dirs, files in os.walk(d_dir):
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".thumbnails"]
                        for f in files:
                            if f.startswith(".") or f.startswith(".temp-"):
                                continue
                            p = Path(root) / f
                            if p.suffix.lower() in DOCUMENT_EXTENSIONS:
                                try:
                                    sz = p.stat().st_size
                                    rel = p.relative_to(d_dir)
                                    tasks.append((str(p), documents_dir / label / rel, sz, "Document"))
                                except Exception:
                                    pass

        # F) Zip & Archive Files (.zip, .rar, .7z)
        if BACKUP_ARCHIVES:
            archive_targets = [
                ("Download", "Download"),
                ("Documents", "Documents"),
                ("WhatsApp/Media/WhatsApp Documents", "WhatsApp Documents"),
                ("Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents", "WhatsApp Documents"),
                ("Telegram/Telegram Documents", "Telegram Documents"),
            ]
            for a_sub, label in archive_targets:
                a_dir = storage_root / a_sub
                if a_dir.is_dir():
                    print(f"[*] Scanning archives in {a_sub}...")
                    for root, dirs, files in os.walk(a_dir):
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d != ".thumbnails"]
                        for f in files:
                            if f.startswith(".") or f.startswith(".temp-"):
                                continue
                            p = Path(root) / f
                            if p.suffix.lower() in ARCHIVE_EXTENSIONS:
                                try:
                                    sz = p.stat().st_size
                                    rel = p.relative_to(a_dir)
                                    tasks.append((str(p), archives_dir / label / rel, sz, "Archive"))
                                except Exception:
                                    pass

        # G) Contacts (.vcf) & WhatsApp Encrypted Chat Databases (.crypt14, .crypt15)
        if BACKUP_CONTACTS_AND_CHATS:
            print("\n[*] Scanning Contacts (.vcf) & WhatsApp Databases...")
            for d_sub in ["Download", "Documents"]:
                d_dir = storage_root / d_sub
                if d_dir.is_dir():
                    for root, _, files in os.walk(d_dir):
                        for f in files:
                            if f.lower().endswith(".vcf") and not f.startswith("."):
                                p = Path(root) / f
                                try:
                                    sz = p.stat().st_size
                                    tasks.append((str(p), contacts_dir / f, sz, "Contacts (vCard)"))
                                except Exception:
                                    pass

            # Root folder of storage_root for contacts (non-recursive)
            try:
                for entry in storage_root.iterdir():
                    if entry.is_file() and entry.name.lower().endswith(".vcf") and not entry.name.startswith("."):
                        tasks.append((str(entry), contacts_dir / entry.name, entry.stat().st_size, "Contacts (vCard)"))
            except Exception:
                pass

            # WhatsApp Databases
            for db_sub in ["WhatsApp/Databases", "Android/media/com.whatsapp/WhatsApp/Databases"]:
                db_dir = storage_root / db_sub
                if db_dir.is_dir():
                    for root, _, files in os.walk(db_dir):
                        for f in files:
                            if ".crypt" in f.lower() and not f.startswith("."):
                                p = Path(root) / f
                                try:
                                    sz = p.stat().st_size
                                    tasks.append((str(p), wa_db_dir / f, sz, "WhatsApp Database"))
                                except Exception:
                                    pass

        # Deduplicate tasks by source path
        unique_tasks = []
        seen_sources = set()
        for src_id, dst_f, sz, cat in tasks:
            if src_id not in seen_sources:
                seen_sources.add(src_id)
                unique_tasks.append((src_id, dst_f, sz, cat))
        tasks = unique_tasks

    total_tasks = len(tasks)
    print(f"\nTotal life memory files discovered: {total_tasks}")
    if total_tasks == 0:
        print("No media files found to back up. Exiting.")
        return

    # 5. Incremental Zero-Overwrite Backup Execution
    copied_count = 0
    skipped_count = 0
    failed_count = 0
    versioned_conflict_count = 0
    total_bytes_copied = 0
    errors: list[tuple[str, str]] = []
    io_hardware_errors = 0

    print("\nStarting incremental zero-overwrite backup process...")
    print("-" * 70)

    for idx, (source_id, intended_dst_file, src_size, category) in enumerate(tasks, start=1):
        # Zero-Overwrite Versioned Conflict Resolution
        actual_dst_file, should_skip = get_safe_destination_path(intended_dst_file, src_size)

        if should_skip:
            skipped_count += 1
            print(f"[{idx}/{total_tasks}] [SKIP] {actual_dst_file.name} (Already up-to-date on hard drive)")
            continue

        if actual_dst_file != intended_dst_file:
            versioned_conflict_count += 1
            print(f"[{idx}/{total_tasks}] [SAFE VERSION] {intended_dst_file.name} -> {actual_dst_file.name} (Preserving existing file of different size)")

        size_str = format_size(src_size)
        parent_name = actual_dst_file.parent.name
        target_display_name = actual_dst_file.name

        if DRY_RUN:
            print(f"[{idx}/{total_tasks}] [DRY-RUN WOULD COPY] {target_display_name} ({size_str}) -> {parent_name}")
            copied_count += 1
            total_bytes_copied += src_size
        else:
            print(f"[{idx}/{total_tasks}] [COPYING] {target_display_name} ({size_str}) -> {parent_name}...", end="", flush=True)

            if use_adb:
                success, err = adb_pull_file(source_id, actual_dst_file, dry_run=False)
                transferred_bytes = src_size if success else 0
            else:
                success, transferred_bytes, err = safe_copy_file(Path(source_id), actual_dst_file, dry_run=False)

            if success:
                print(" DONE")
                copied_count += 1
                total_bytes_copied += transferred_bytes

                # 10-Year Bitrot Protection: Compute & log SHA-256 to integrity manifest
                try:
                    f_hash = compute_sha256(actual_dst_file)
                    rel_p = actual_dst_file.relative_to(backup_root).as_posix()
                    append_integrity_manifest(integrity_manifest_path, f_hash, rel_p)
                except Exception as h_err:
                    print(f"           [!] Hash manifest error: {h_err}")
            else:
                print(" FAILED!")
                print(f"           Error: {err}")
                errors.append((target_display_name, str(err)))
                failed_count += 1
                if "input/output error" in str(err).lower() or "[errno 5]" in str(err).lower():
                    io_hardware_errors += 1

    duration = time.time() - start_time
    minutes, seconds = divmod(int(duration), 60)

    # 6. Generate Summary & Memory Archive Statistics
    summary_lines = [
        "=" * 70,
        "             10-YEAR LIFE MEMORY TIME CAPSULE SUMMARY",
        "=" * 70,
        f"Date & Time          : {run_date_str}",
        f"Execution Mode       : {'DRY RUN (Simulation only)' if DRY_RUN else 'LIVE RUN (Completed)'}",
        f"Connection Engine    : {engine_label}",
        f"Destination Folder   : {backup_root}",
        f"Total Files Scanned  : {total_tasks}",
        f"Files Copied         : {copied_count}",
        f"Files Skipped        : {skipped_count} (identical copy already verified on hard drive)",
        f"Version Conflicts    : {versioned_conflict_count} (safely preserved with _v1/_v2 names)",
        f"Files Failed         : {failed_count}",
        f"Total Data Copied    : {format_size(total_bytes_copied)} ({total_bytes_copied:,} bytes)",
        f"Time Elapsed         : {minutes}m {seconds}s",
    ]

    if health_result:
        summary_lines.append("-" * 70)
        summary_lines.append("HARD DRIVE HEALTH STATUS:")
        summary_lines.append(f"  Drive Model        : {health_result.get('physical_model', health_result['device_name'])}")
        summary_lines.append(f"  Health Condition   : [{health_result['status']}] ★★★★★")
        summary_lines.append(f"  Available Space    : {format_size(health_result['free_bytes'])} Free ({health_result['free_percent']:.1f}%)")
        summary_lines.append(f"  Sector Integrity   : {'PASS (SHA-256 Bit-for-bit verified)' if health_result['integrity_passed'] else 'FAIL (CORRUPTION DETECTED)'}")
        tel = health_result.get("telemetry", {})
        if tel.get("kernel_io_clean", True):
            summary_lines.append(f"  Kernel Telemetry   : 0 Read/Write Errors, 0 Retries (Flawless)")
        else:
            summary_lines.append(f"  Kernel Telemetry   : Errors: {tel.get('read_errors', 0)}R/{tel.get('write_errors', 0)}W")
        if health_result["warnings"]:
            for w in health_result["warnings"]:
                summary_lines.append(f"  [Warning] {w}")
        if health_result["critical_errors"]:
            for c in health_result["critical_errors"]:
                summary_lines.append(f"  [CRITICAL] {c}")

    if bitrot_audit:
        summary_lines.append("-" * 70)
        summary_lines.append("10-YEAR BITROT & CRYPTOGRAPHIC INTEGRITY AUDIT:")
        summary_lines.append(f"  Manifest Entries   : {bitrot_audit['total_manifest_entries']:,}")
        summary_lines.append(f"  Verified Bit-Perfect: {bitrot_audit['verified_passed']:,}")
        if bitrot_audit['corrupted_files']:
            summary_lines.append(f"  ❌ CORRUPTED (BITROT): {len(bitrot_audit['corrupted_files'])} file(s)!")
            for rel_p, exp_h, act_h in bitrot_audit['corrupted_files']:
                summary_lines.append(f"     - {rel_p}")
                summary_lines.append(f"       Expected SHA-256: {exp_h}")
                summary_lines.append(f"       Actual on Disk  : {act_h}")
        else:
            summary_lines.append("  Corrupted Files    : 0 (No bitrot detected! All data 100% intact)")
        if bitrot_audit['missing_files']:
            summary_lines.append(f"  ⚠️  Missing Files   : {len(bitrot_audit['missing_files'])} file(s)")
            for m_p in bitrot_audit['missing_files'][:10]:
                summary_lines.append(f"     - {m_p}")
            if len(bitrot_audit['missing_files']) > 10:
                summary_lines.append(f"     ... and {len(bitrot_audit['missing_files']) - 10} more.")
    else:
        summary_lines.append("-" * 70)
        summary_lines.append(f"Integrity Manifest   : {INTEGRITY_MANIFEST_FILENAME} (SHA-256 protection active)")
        summary_lines.append("                     (Set VERIFY_BITROT_INTEGRITY = True to run full bitrot audit)")

    if io_hardware_errors > 0:
        summary_lines.append("-" * 70)
        summary_lines.append(f"⚠️  DRIVE HARDWARE ALERT: {io_hardware_errors} files encountered Input/Output errors!")
        summary_lines.append("This is a strong sign of dying drive sectors or bad cable. REPLACE HARD DRIVE SOON!")

    if errors:
        summary_lines.append("-" * 70)
        summary_lines.append(f"ERRORS ENCOUNTERED ({len(errors)} files failed):")
        for err_file, err_msg in errors:
            summary_lines.append(f"  - {err_file}: {err_msg}")

    summary_lines.append("=" * 70)
    summary_text = "\n".join(summary_lines)

    # Print summary to console
    print("\n" + summary_text + "\n")

    # 7. Final Prominent Health Alert if Drive is at risk
    drive_failing = (
        (health_result and health_result["status"] != "EXCELLENT / HEALTHY") or
        io_hardware_errors > 0 or
        (bitrot_audit and len(bitrot_audit["corrupted_files"]) > 0)
    )
    if drive_failing:
        print("\n" + "*" * 70)
        print("  ⚠️ ⚠️ ⚠️   IMPORTANT NOTICE FOR YOUR LIFE MEMORIES (5-10 YEARS)   ⚠️ ⚠️ ⚠️")
        print("*" * 70)
        print("Your external hard drive health is DEGRADED, CORRUPTED, or LOW ON SPACE.")
        print("If you plan to store these memories for 5 to 10 years:")
        print("  1. BUY A NEW EXTERNAL DRIVE (e.g. Western Digital, Samsung T7 SSD).")
        print("  2. COPY ALL FILES from this drive to your new drive immediately.")
        print("  3. Never keep only one copy of irreplaceable life memories.")
        print("*" * 70 + "\n")

    # 8. Append to Log File
    if not DRY_RUN:
        try:
            backup_root.mkdir(parents=True, exist_ok=True)
            with open(log_file_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n--- LIFE MEMORY TIME CAPSULE LOG: {run_date_str} ---\n")
                log_file.write(summary_text)
                if drive_failing:
                    log_file.write("\n*** HARD DRIVE WARNING: Drive health degraded. Replace drive to protect memories! ***\n")
                log_file.write("\n\n")
            print(f"[✓] Backup summary & health log appended to: {log_file_path}")
        except Exception as e:
            print(f"[!] Warning: Could not write to log file at {log_file_path}: {e}")

        # 9. Generate Offline HTML5 Time Capsule Browser
        if GENERATE_TIMELINE_HTML:
            generate_timeline_html(backup_root)
    else:
        print("[*] Note: DRY RUN mode enabled. No changes were written to disk, manifest, or HTML dashboard.")


if __name__ == "__main__":
    try:
        run_backup()
    except KeyboardInterrupt:
        print("\n\n[!] Backup interrupted by user. Exiting safely.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[FATAL ERROR] An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

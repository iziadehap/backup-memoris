# Samsung Phone to External Hard Drive - Life Memory Backup & Health Tool for macOS

A Python 3 backup utility designed to preserve your life memories (photos, camera videos, screenshots, voice recorder memos, call notes, and WhatsApp media) for the next 5 to 10+ years on your external hard drive (`/Volumes/Backup_data`).

---

## Connection Modes

### 1. Direct ADB USB Mode (Recommended - 100% Free)
**No MacDroid or paid apps needed!** 
The script automatically connects directly to your Samsung phone (`SM-S9080`) over USB via Android Debug Bridge.
- Full USB 3.0 speed.
- Completely free and unlimited transfers.
- Does not drop connection or freeze during large 30GB+ video backups.

### 2. Mounted Volume Mode (Optional)
If you ever mount the phone as a folder under `/Volumes/` (e.g. using MacDroid), the script can also read from there.

---

## Folder Structure on Your Hard Drive

Backups are organized under `/Volumes/Backup_data/Backup/`:

```
/Volumes/Backup_data/Backup/
├── Camera Photos/             # Photos taken with phone camera (*.jpg, *.heic, *.dng, *.png, etc.)
├── Videos/                    # Videos recorded with camera (*.mp4, *.mov, *.3gp, *.mkv)
├── Screenshots/               # Screenshots and screen recordings
├── Voice & Audio Recordings/  # Voice memos, call recordings, audio notes, WhatsApp voice notes
├── Other Pictures & Media/    # Pictures & videos from Pictures/, WhatsApp, Downloads, etc.
├── Documents/                 # PDF files, Word (.doc/.docx), text, office documents
├── Zip & Archives/            # ZIP, RAR, 7z archive files
└── backup_log.txt             # Persistent log with timestamps & drive health diagnostic reports
```

---

## Hard Drive Health Diagnostic (Every Run)

Because you are creating this archive to last for 5 to 10 years, the script tests your hard drive hardware on every run:
1. **S.M.A.R.T. Status & Filesystem**: Checks if hardware failure flags or read-only states have been triggered.
2. **Free Storage Space**: Warns you if the drive has less than 20 GB or 10% remaining.
3. **Sector & Data Integrity Test**: Writes diagnostic test data, measures write latency, and verifies it bit-for-bit with SHA-256 to detect dying sectors or silent data corruption.
4. **Failure Alert**: If the hard drive begins degrading, the script alerts you to replace it immediately before data is lost.

---

## How to Run the Backup

### Option A: Double-Click in Finder
Double-click [`run_backup.command`](file:///Users/axon/Desktop/Workspace/ather/backup%20files/run_backup.command). A macOS Terminal window will open, show real-time progress, print the summary and health report, and wait for you to press `[Enter]` before closing.

### Option B: Terminal Command
```bash
cd "/Users/axon/Desktop/Workspace/ather/backup files"
python3 backup.py
```

---

## Configuration Settings in `backup.py`

You can customize anything in the top section of [`backup.py`](file:///Users/axon/Desktop/Workspace/ather/backup%20files/backup.py):
- `DRY_RUN = False` (Set to `True` if you only want to simulate without writing).
- `BACKUP_CAMERA_MEDIA = True` (Camera photos and videos).
- `BACKUP_SCREENSHOTS = True` (Screenshots).
- `BACKUP_VOICE_AUDIO = True` (Voice recorder, voice notes, audio).
- `BACKUP_OTHER_MEMORIES = True` (WhatsApp, Pictures, Downloads).
- `CHECK_DRIVE_HEALTH = True` (Drive hardware diagnostic).

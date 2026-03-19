import os
import sys
import time
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} INPUT_PATH OUTPUT_ZIP", file=sys.stderr)
    sys.exit(2)

input_path = Path(sys.argv[1]).resolve()
output_zip = Path(sys.argv[2]).resolve()

if not input_path.is_file():
    print(f"Input file does not exist: {input_path}", file=sys.stderr)
    sys.exit(3)

output_zip.parent.mkdir(parents=True, exist_ok=True)

tmp_dir = output_zip.parent / f"{output_zip.stem}_tmp"
tmp_dir.mkdir(parents=True, exist_ok=True)

try:
    summary_path = tmp_dir / "summary.txt"
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    summary = (
        f"Input video: {input_path}\n"
        f"Processed at: {ts}\n"
        "Status: success\n"
    )
    summary_path.write_text(summary, encoding="utf-8")

    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(tmp_dir):
            for name in files:
                fpath = Path(root) / name
                arcname = fpath.relative_to(tmp_dir)
                zf.write(fpath, arcname.as_posix())

finally:
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
        print(f"Cleaned up: {tmp_dir}")
    else:
        print(f"No temporary directory to clean up: {tmp_dir}")

sys.exit(0)
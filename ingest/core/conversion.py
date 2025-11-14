from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def convert_rtf_to_docx(source: str | Path, destination: str | Path) -> None:
	"""
	Converts an RTF document to DOCX using LibreOffice in headless mode.

	The destination file is rewritten when the source has been modified more recently.
	"""
	src_path = Path(source).expanduser().resolve()
	dest_path = Path(destination).expanduser().resolve()

	if not src_path.exists():
		raise FileNotFoundError(f"RTF source {src_path} does not exist")

	dest_path.parent.mkdir(parents=True, exist_ok=True)

	if dest_path.exists() and dest_path.stat().st_mtime >= src_path.stat().st_mtime:
		return  # Existing conversion is up-to-date.

	with tempfile.TemporaryDirectory(prefix="taxiv_rtf_convert_") as tmpdir:
		cmd = [
			"soffice",
			"--headless",
			"--convert-to",
			"docx",
			"--outdir",
			tmpdir,
			str(src_path),
		]
		result = subprocess.run(cmd, capture_output=True, text=True)
		if result.returncode != 0:
			raise RuntimeError(
				f"LibreOffice conversion failed for {src_path}: {result.stderr.strip() or result.stdout.strip()}"
			)
		candidates = [
			path for path in Path(tmpdir).iterdir()
			if path.suffix.lower() == ".docx"
		]
		if not candidates:
			raise RuntimeError(
				f"LibreOffice did not emit a DOCX for {src_path} "
				f"(stdout: {result.stdout.strip()} stderr: {result.stderr.strip()})"
			)
		produced = candidates[0]
		shutil.move(str(produced), dest_path)

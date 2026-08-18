from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
PACKAGE_DIR = BUILD_DIR / "package"
ZIP_PATH = BUILD_DIR / "lambda_deploy.zip"

PYTHON_VERSION = "3.12"


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main():
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    PACKAGE_DIR.mkdir(parents=True)

    run([
        sys.executable, "-m", "pip", "install",
        "-r", str(REPO_ROOT / "requirements.txt"),
        "--target", str(PACKAGE_DIR),
        "--platform", "manylinux2014_x86_64",
        "--only-binary", ":all:",
        "--python-version", PYTHON_VERSION,
        "--implementation", "cp",
    ])


    shutil.copytree(REPO_ROOT / "src", PACKAGE_DIR / "src")


    for bundled_pkg in ("boto3", "botocore", "s3transfer", "jmespath"):
        for path in PACKAGE_DIR.glob(f"{bundled_pkg}*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    for junk in PACKAGE_DIR.rglob("__pycache__"):
        shutil.rmtree(junk, ignore_errors=True)

    print(f"Zipping {PACKAGE_DIR} -> {ZIP_PATH}")
    shutil.make_archive(str(ZIP_PATH.with_suffix("")), "zip", root_dir=str(PACKAGE_DIR))

    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"\nDone: {ZIP_PATH} ({size_mb:.1f} MB)")
    if size_mb > 50:
        print(
            "WARNING: over the 50MB direct-upload limit for the Lambda console/CLI zip upload. "
            "Upload via S3 instead (aws lambda update-function-code --s3-bucket ... --s3-key ...), "
            "or switch to a container image if this grows further."
        )


if __name__ == "__main__":
    main()

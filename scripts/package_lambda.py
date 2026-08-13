"""
Builds the Lambda deployment zip. Run from the repo root on Windows
(cmd.exe): python scripts\\package_lambda.py

Why this can't be a plain `pip install -r requirements.txt`: this repo
is developed on Windows, but Lambda runs Amazon Linux. Two dependencies
(psycopg[binary], and lxml via trafilatura) ship compiled C extensions --
a normal Windows pip install downloads Windows .pyd binaries, which will
import-error on Lambda with no useful error message pointing at the real
cause. --platform manylinux2014_x86_64 --only-binary=:all: forces pip to
fetch the prebuilt Linux wheels from PyPI instead of building/downloading
for the local platform -- no Docker or Linux machine required, since all
of this repo's dependencies publish manylinux wheels already.

Output: build/lambda_deploy.zip, structured with `src/` at the zip root
so the Lambda handler string src.agent.lambda_handler.handler resolves.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
PACKAGE_DIR = BUILD_DIR / "package"
ZIP_PATH = BUILD_DIR / "lambda_deploy.zip"

# Match this to the Lambda function's configured runtime.
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

    # Copy application code into the package root alongside the
    # installed dependencies, so `src.agent.lambda_handler` is importable
    # from the zip root.
    shutil.copytree(REPO_ROOT / "src", PACKAGE_DIR / "src")

    # Lambda's Python runtime already bundles boto3/botocore/s3transfer/
    # jmespath -- shipping our own copies just bloats the zip (botocore
    # alone is ~16MB) for no benefit unless you need a newer boto3 than
    # the runtime ships, which this project doesn't.
    for bundled_pkg in ("boto3", "botocore", "s3transfer", "jmespath"):
        for path in PACKAGE_DIR.glob(f"{bundled_pkg}*"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    # Test/dev-only files have no place in the deployed artifact.
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

"""Download the public bulk source files into data/raw/ and record a manifest.

Usage:
    python scripts/download_sources.py            # all sources
    python scripts/download_sources.py hmdd hgnc  # selected sources

Each download is recorded in data/raw/manifest.json with URL, size, SHA-256
and timestamp so imports can be traced to an exact file. Files are only
downloaded from the providers' documented download locations.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
SOURCES = {
    "hmdd": ("HMDD v3.2 all data", "http://www.cuilab.cn/static/hmdd3/data/alldata.txt", "hmdd_alldata.txt"),
    "lncrnadisease": ("LncRNADisease v3.0 all data",
                      "http://www.rnanut.net/lncrnadisease/static/download/website_alldata.tsv",
                      "lncrnadisease_website_alldata.tsv"),
    "hgnc": ("HGNC complete set",
             "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt",
             "hgnc_complete_set.txt"),
}


def _fetch_resumable(url, tmp, attempts=30):
    """Stream ``url`` into ``tmp``, resuming with HTTP Range requests after dropped connections."""
    total = None
    for attempt in range(1, attempts + 1):
        have = tmp.stat().st_size if tmp.exists() else 0
        headers = {"User-Agent": "ncRNAAtlas/1.0"}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with requests.get(url, stream=True, timeout=(15, 120), headers=headers) as r:
                if r.status_code == 416:  # already complete
                    return
                r.raise_for_status()
                if have and r.status_code != 206:  # server ignored Range: start over
                    have = 0
                if r.status_code == 206 and "Content-Range" in r.headers:
                    total = int(r.headers["Content-Range"].rsplit("/", 1)[1])
                elif "Content-Length" in r.headers:
                    total = have + int(r.headers["Content-Length"])
                with tmp.open("ab" if have else "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        fh.write(chunk)
            if total is None or tmp.stat().st_size >= total:
                return
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
            print(f"  attempt {attempt} interrupted ({exc.__class__.__name__}); "
                  f"{tmp.stat().st_size if tmp.exists() else 0:,} bytes so far, resuming...", flush=True)
    raise requests.ConnectionError(f"download incomplete after {attempts} attempts")


def download(key):
    label, url, filename = SOURCES[key]
    target = RAW / filename
    tmp = target.with_suffix(target.suffix + ".part")
    origin = target.with_suffix(target.suffix + ".part.url")
    # Resume a partial file only if a previous run recorded that it came from this exact URL.
    if tmp.exists() and not (origin.exists() and origin.read_text().strip() == url):
        tmp.unlink()
    origin.write_text(url)
    print(f"Downloading {label} from {url} ...", flush=True)
    _fetch_resumable(url, tmp)
    origin.unlink()
    sha = hashlib.sha256()
    with tmp.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            sha.update(chunk)
    size = tmp.stat().st_size
    tmp.replace(target)
    print(f"  saved {target.name}: {size:,} bytes, sha256 {sha.hexdigest()[:16]}...")
    return {"label": label, "url": url, "file": filename, "bytes": size, "sha256": sha.hexdigest(),
            "downloaded_at": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", help=f"sources to download: {', '.join(SOURCES)} (default: all)")
    args = parser.parse_args()
    unknown = [s for s in args.sources if s not in SOURCES]
    if unknown:
        parser.error(f"unknown source(s): {', '.join(unknown)}")
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    failed = []
    for key in args.sources or SOURCES:
        try:
            manifest[key] = download(key)
        except requests.RequestException as exc:
            print(f"  FAILED: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            failed.append(key)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    if failed:
        print(f"Failed: {', '.join(failed)}. The provider may be temporarily unavailable; retry later.",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

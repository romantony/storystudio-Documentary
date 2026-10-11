"""Copy the finished outputs listed in status.json to the output bucket and record a public URL for each.
python3 -m docgen upload --prefix docgen/<request_id>/

Only files registered with `status --output kind=path` are uploaded; assets and intermediate files stay in the run folder.
Env: DOCGEN_OUTPUT_BUCKET (S3 bucket, or an R2 bucket with DOCGEN_S3_ENDPOINT), DOCGEN_OUTPUT_BASE_URL (the CDN in front of
the bucket, for example https://cdn-v2.ai-storystudio.com). Each output gains "bucket", "key" and, with a base URL, "url".
Without a bucket, files stay in the run folder and a warning is added to the status."""
import mimetypes, os, sys
from urllib.parse import quote
from . import status
TYPES = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".md": "text/markdown; charset=utf-8",
         ".json": "application/json", ".txt": "text/plain; charset=utf-8", ".srt": "text/plain; charset=utf-8"}

def main(cmd, argv):
    prefix = argv[argv.index("--prefix") + 1] if "--prefix" in argv else f"docgen/{os.path.basename(os.getcwd())}/"
    st = status.read(); bucket = os.environ.get("DOCGEN_OUTPUT_BUCKET"); base = (os.environ.get("DOCGEN_OUTPUT_BASE_URL") or "").rstrip("/")
    if not bucket:
        status.update(warn=["Outputs were not uploaded: DOCGEN_OUTPUT_BUCKET is not set. Files are in the run folder."]); print("no bucket; skipped"); return
    import boto3
    s3 = boto3.client("s3", endpoint_url=os.environ.get("DOCGEN_S3_ENDPOINT") or None)
    failed = []
    for o in st.get("outputs", []):
        p = o["path"]
        if not os.path.isfile(p): failed.append(f"{p} (file missing)"); print("missing", p); continue
        k = prefix.strip("/") + "/" + p.lstrip("./")
        ctype = TYPES.get(os.path.splitext(p)[1].lower()) or mimetypes.guess_type(p)[0] or "application/octet-stream"
        try: s3.upload_file(p, bucket, k, ExtraArgs={"ContentType": ctype})
        except Exception as e: failed.append(f"{p} ({type(e).__name__})"); print("failed", p, e); continue
        o.update(key=k, bucket=bucket, bytes=os.path.getsize(p))
        if base: o["url"] = base + "/" + quote(k)
        print("uploaded", o.get("url") or f"s3://{bucket}/{k}")
    status.write(st)
    if failed:
        status.update(warn=["Not uploaded: " + ", ".join(failed)]); sys.exit(1)

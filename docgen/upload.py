"""Copy the finished outputs listed in status.json to an S3-compatible bucket (S3, or R2 with DOCGEN_S3_ENDPOINT).
python3 -m docgen upload --prefix docgen/<request_id>/
Needs DOCGEN_OUTPUT_BUCKET. Without it, files stay in the run folder and a warning is added to the status."""
import os, sys
from . import status
def main(cmd, argv):
    prefix = argv[argv.index("--prefix") + 1] if "--prefix" in argv else f"docgen/{os.path.basename(os.getcwd())}/"
    st = status.read(); bucket = os.environ.get("DOCGEN_OUTPUT_BUCKET")
    if not bucket:
        status.update(warn=["Outputs were not uploaded: DOCGEN_OUTPUT_BUCKET is not set. Files are in the run folder."]); print("no bucket; skipped"); return
    import boto3
    s3 = boto3.client("s3", endpoint_url=os.environ.get("DOCGEN_S3_ENDPOINT") or None)
    for o in st.get("outputs", []):
        p = o["path"]
        if not os.path.exists(p): print("missing", p); continue
        k = prefix.rstrip("/") + "/" + p; s3.upload_file(p, bucket, k); o["key"] = k; o["bucket"] = bucket; o["bytes"] = os.path.getsize(p); print("uploaded", k)
    status.write(st)

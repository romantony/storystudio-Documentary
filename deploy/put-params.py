#!/usr/bin/env python3
"""Store the service's secrets in SSM Parameter Store under /docgen/ (SecureString). Run once, by a person, with AWS credentials.

API keys are read from the environment (ANTHROPIC_API_KEY, GEMINI_API_KEY, RUNPOD_API_KEY, COMFY_API_KEY, KIE_API_KEY), with the
DOCGEN_KEYS_DOC fallback of docgen.common for the last three. The API token, callback secret, origin secret and desktop
password are generated. Existing parameters are left alone unless --overwrite is given. Values are never printed.
Run from the repository root: python3 deploy/put-params.py
"""
import os, secrets, sys
import boto3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from docgen.common import key

ssm = boto3.client("ssm", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
overwrite = "--overwrite" in sys.argv
have = set()
for page in ssm.get_paginator("describe_parameters").paginate(ParameterFilters=[{"Key": "Name", "Option": "BeginsWith", "Values": ["/docgen/"]}]):
    have |= {p["Name"] for p in page["Parameters"]}

vals = {n: key(n) for n in ("RUNPOD_API_KEY", "GEMINI_API_KEY", "COMFY_API_KEY")}
if os.environ.get("KIE_API_KEY"): vals["KIE_API_KEY"] = os.environ["KIE_API_KEY"]   # cinematic thumbnails (Nano Banana 2.1); optional
for n in ("FRED_API_KEY", "EIA_API_KEY", "BLS_API_KEY"):   # chart data (docgen data); optional, free to register
    if os.environ.get(n): vals[n] = os.environ[n]
if os.environ.get("ANTHROPIC_API_KEY"): vals["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
else: print("ANTHROPIC_API_KEY is not in the environment: skipped, add it later")
vals.update(DOCGEN_API_TOKEN=secrets.token_hex(32), DOCGEN_CALLBACK_SECRET=secrets.token_hex(32),
            DOCGEN_ORIGIN_SECRET=secrets.token_hex(32), VNC_PASSWORD=secrets.token_hex(4))
for n, v in vals.items():
    name = "/docgen/" + n
    if name in have and not overwrite: print("exists, left alone:", name); continue
    ssm.put_parameter(Name=name, Value=v, Type="SecureString", Overwrite=True)
    print("stored:", name, f"({len(v)} characters)")

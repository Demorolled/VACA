#!/usr/bin/env python3
"""Cancel the running Kaggle Sky1 kernel session."""
import sys

from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import (
    ApiGetKernelRequest,
    ApiCancelKernelSessionRequest,
)

OWNER = "stevenawoods"
SLUG = "vaca-qlora-round-sky1"


def main():
    api = KaggleApi()
    api.authenticate()
    client = api.build_kaggle_client()
    kc = client.kernels.kernels_api_client

    # Discover the numeric id of the kernel (the running session keys on this).
    gk = ApiGetKernelRequest()
    gk.user_name = OWNER
    gk.kernel_slug = SLUG
    try:
        meta = kc.get_kernel(gk)._metadata
        kid = meta._id
    except Exception as e:
        print("get_kernel err:", type(e).__name__, str(e)[:200])
        return 1
    print("kernel id:", kid)

    cancel = ApiCancelKernelSessionRequest()
    cancel.kernel_session_id = int(kid)
    try:
        out = kc.cancel_kernel_session(cancel)
        print("CANCEL OK →", out._error_message)
        print("✅ cancel requested for session", kid)
    except Exception as e:
        print("cancel failed:", type(e).__name__, str(e)[:300])
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
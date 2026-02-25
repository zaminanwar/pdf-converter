"""Corporate SSL fix (Zscaler) and Windows symlink fallback.

Import this module before any network calls to ensure SSL works
behind corporate proxies with Zscaler certificate inspection.
"""

import os
import sys
import shutil
import base64
from pathlib import Path


def setup_ssl():
    """Create a combined CA bundle with certifi roots + decoded Zscaler cert."""
    zscaler_pem = Path(os.path.expanduser("~")) / "zscaler-root-new.pem"
    if not zscaler_pem.exists():
        return  # No Zscaler cert found, skip

    combined = Path(__file__).parent / "_combined-ca-bundle.pem"
    if combined.exists():
        # Already created — just set env vars
        combined_str = str(combined)
        os.environ["SSL_CERT_FILE"] = combined_str
        os.environ["REQUESTS_CA_BUNDLE"] = combined_str
        os.environ["CURL_CA_BUNDLE"] = combined_str
        return

    try:
        import certifi

        # Read and decode the double-encoded Zscaler cert
        raw = zscaler_pem.read_text()
        lines = raw.strip().splitlines()
        b64 = "".join(l.strip() for l in lines if not l.startswith("-----"))
        real_cert = base64.b64decode(b64).decode("utf-8")

        # Combine certifi bundle + decoded Zscaler cert
        certifi_bundle = Path(certifi.where()).read_text()
        combined.write_text(
            certifi_bundle.rstrip()
            + "\n\n# Zscaler Root CA\n"
            + real_cert.strip()
            + "\n"
        )

        combined_str = str(combined)
        os.environ["SSL_CERT_FILE"] = combined_str
        os.environ["REQUESTS_CA_BUNDLE"] = combined_str
        os.environ["CURL_CA_BUNDLE"] = combined_str
    except Exception as e:
        print(f"  Warning: Could not set up combined CA bundle: {e}", file=sys.stderr)


def setup_symlink_fallback():
    """Fall back to copy if Windows symlinks fail (requires Developer Mode)."""
    _orig_symlink = os.symlink

    def _safe_symlink(src, dst, *args, **kwargs):
        try:
            _orig_symlink(src, dst, *args, **kwargs)
        except OSError:
            src_abs = (
                src
                if os.path.isabs(src)
                else os.path.join(os.path.dirname(dst), src)
            )
            shutil.copy2(src_abs, dst)

    os.symlink = _safe_symlink


# Apply fixes on import
setup_ssl()
setup_symlink_fallback()

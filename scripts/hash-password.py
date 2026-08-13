#!/usr/bin/env python3
"""SHA1 helper matching MagnusBilling pkg_user.password."""
import hashlib
import sys

if len(sys.argv) != 2:
    print("usage: hash-password.py <plain-password>", file=sys.stderr)
    raise SystemExit(2)
print(hashlib.sha1(sys.argv[1].encode()).hexdigest())

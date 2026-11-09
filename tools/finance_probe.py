#!/usr/bin/env python3
"""Read-only source-contract probe. Prints schema/counts, never customer rows."""
import argparse
from collections import Counter
import http.cookiejar
import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, HTTPCookieProcessor, build_opener

if __package__:
    from .finance_credentials import read_private_json
else:
    from finance_credentials import read_private_json

ORIGIN = "https://chessaction.com"


class SameOrigin(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlsplit(newurl)
        if u.scheme != "https" or u.netloc != "chessaction.com":
            raise ValueError("Refused a cross-origin redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("credentials", type=Path)
    p.add_argument("--tournament", default="4531", help="Numeric Chess Action tournament ID")
    args = p.parse_args()
    if not args.tournament.isdigit():
        p.error("A numeric tournament ID is required")
    credentials = read_private_json(args.credentials)
    cookie_jar = http.cookiejar.CookieJar()
    opener = build_opener(SameOrigin(), HTTPCookieProcessor(cookie_jar))

    def read(path, data=None):
        request = Request(ORIGIN + (path if path.startswith('/') else "/admin/" + path),
                          data=urlencode(data).encode() if data is not None else None,
                          headers={"User-Agent": "Mozilla/5.0 ChessEntries/1.0", "Origin": ORIGIN,
                                   "Referer": ORIGIN + ("/login.php" if path == "/login.php" else "/admin/search.php")})
        with opener.open(request, timeout=25) as response:
            body = response.read(10_000_001)
            if len(body) > 10_000_000:
                raise ValueError("Response exceeds the probe limit")
            return response.url, body.decode("utf-8", errors="replace")

    cookie = credentials.get('CHESS_ACTION_COOKIE')
    if not isinstance(cookie, str) or not cookie or any(c in cookie for c in '\r\n'):
        raise ValueError('source_session_required')
    opener.addheaders = [('Cookie', cookie)]
    url, page = read('search.php')
    if 'login.php' in url or not re.search(r'id\s*=\s*["\']tournments["\']', page):
        raise ValueError('source_session_expired')
    print('Authenticated session reuse verified')
    probe_orders(args, read)


def probe_orders(args, read):
    filters = dict(pptxn="", lname="", fname="", ftitles="all", uscfid="", ppcon="0",
                   country="0", state="All", mem="0", tname=args.tournament, excludeper="0",
                   discountClaimed="0", regularDiscountCode="", additionalFee="0",
                   sortingOption="1", sortBy="paymentDate", selectedReportType="player_tabular_datatable",
                   orderStatus="Non-Declined", draw="1", start="0", length="100")
    _, response = read("set_player_data_for_datatable.php", filters)
    result = json.loads(response)
    rows = result.get("data", [])
    print(json.dumps({"response_fields": sorted(result), "total": result.get("recordsTotal"),
                      "filtered": result.get("recordsFiltered"), "returned": len(rows),
                      "row_fields": sorted(rows[0]) if rows else [],
                      "statuses": dict(Counter(str(r.get("status")) for r in rows)),
                      "refund_flags": dict(Counter(str(r.get("is_refunded")) for r in rows)),
                      "deleted_flags": dict(Counter(str(r.get("is_deleted")) for r in rows))}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Network exceptions and response bodies can contain account details.
        reasons = {'source_session_expired', 'source_session_required', 'Refused a cross-origin redirect', 'Response exceeds the probe limit'}
        print(json.dumps({"probe_failed": type(error).__name__,
                          "reason": str(error) if type(error) is ValueError and str(error) in reasons else "source_read_failed"}))
        raise SystemExit(1) from None

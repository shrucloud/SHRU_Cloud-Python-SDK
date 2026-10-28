"""Prints your balance and the full service catalog as JSON: every field
place_order() can need (input label, quantity range, extra fields).

Usage: python examples/sync_services.py
"""

import json
import sys

from shrucloud import Client, ShruError

client = Client(
    "https://reseller.example.com",  # the address the platform gave you
    "YOUR_KEY_ID",
    "YOUR_SECRET",
)

try:
    catalog = client.sync_catalog()
except ShruError as error:
    print("Sync failed: " + str(error), file=sys.stderr)
    sys.exit(1)

print(json.dumps(catalog, indent=2, ensure_ascii=False))
print(
    "\n%d service(s) - balance: %.2f %s" % (len(catalog["services"]), catalog["balance"], catalog["currency"]),
    file=sys.stderr,
)

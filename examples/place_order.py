"""Places one order for a service ID and input, then prints the order ID and
its first status.

Usage:   python examples/place_order.py <service_id> <input>
Example: python examples/place_order.py 10 356789101234567
"""

import sys

from shrucloud import Client, ShruError

if len(sys.argv) < 3:
    print("Usage: python examples/place_order.py <service_id> <input>", file=sys.stderr)
    sys.exit(1)

client = Client("https://reseller.example.com", "YOUR_KEY_ID", "YOUR_SECRET")

try:
    # Running the same command again while this order is still queued
    # returns the same order instead of charging twice.
    order = client.place_order(int(sys.argv[1]), sys.argv[2])
except ShruError as error:
    print("Order failed: " + str(error), file=sys.stderr)
    if error.is_auth_error():
        print("Check your Key ID and Secret, and that this machine's IP is on the key's allowlist.", file=sys.stderr)
    sys.exit(1)

print("Order #%d - status: %s" % (order["order_id"], order["status"]))
print("Follow it with: python examples/check_status.py %d" % order["order_id"])

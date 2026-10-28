"""Checks one order every 5 seconds until it leaves queued/processing, then
prints its final status and reply. A real integration would check on a
schedule instead of waiting like this.

Usage: python examples/check_status.py <order_id>
"""

import sys
import time

from shrucloud import Client, ShruError

if len(sys.argv) < 2:
    print("Usage: python examples/check_status.py <order_id>", file=sys.stderr)
    sys.exit(1)

order_id = int(sys.argv[1])
client = Client("https://reseller.example.com", "YOUR_KEY_ID", "YOUR_SECRET")

for attempt in range(1, 61):
    try:
        status = client.check_status(order_id)
    except ShruError as error:
        print("Status check failed: " + str(error), file=sys.stderr)
        sys.exit(1)
    if status["status"] not in ("queued", "processing"):
        print("Order #%d finished as: %s" % (order_id, status["status"]))
        if status["reply"]:
            print("Reply:\n" + status["reply"])
        sys.exit(0)
    print("[%d/60] Order #%d is still %s - checking again in 5s..." % (attempt, order_id, status["status"]))
    time.sleep(5)

print("Gave up after 60 checks - order #%d is still in progress." % order_id, file=sys.stderr)
sys.exit(1)

"""Standalone idempotent backend worker: `python -m restaurant.scheduler`.

Run one worker process alongside Flask. Each tick is safe to retry: waitlist
expiration and preorder promotion use conditional updates/unique queue keys.
"""
from __future__ import annotations

import argparse
import time

from restaurant.db.database import ensure_database, get_connection
from restaurant.services.queue_manager import QueueManager
from restaurant.services.common import ServiceError


def run_scheduled_tasks(now=None):
    expired=QueueManager.expire_called()
    promoted=QueueManager.enqueue_due_preorders(now)
    called=[]
    with get_connection() as db:
        tables=[r[0] for r in db.execute("SELECT table_id FROM dining_tables ORDER BY table_id")]
    for table_id in tables:
        try:
            result=QueueManager.call_next(table_id)
            if result: called.append(result)
        except ServiceError as error:
            if error.code != "TABLE_UNAVAILABLE": raise
    return {"expired_waitlist":expired,"promoted_preorders":promoted,"called_parties":called}


def main():
    parser=argparse.ArgumentParser(description="Run the Usurpers backend background scheduler")
    parser.add_argument("--interval",type=int,default=15,help="poll interval in seconds")
    args=parser.parse_args()
    if args.interval < 1: parser.error("--interval must be positive")
    ensure_database()
    while True:
        run_scheduled_tasks()
        time.sleep(args.interval)


if __name__=="__main__": main()

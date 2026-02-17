import asyncio
import logging
import signal
from typing import List
from src.workers.chat_worker import ChatWorker
from src.workers.favorites_worker import FavoritesWorker
from src.workers.trip_worker import TripWorker
logger = logging.getLogger(__name__)


async def main():
    workers = [ChatWorker(), FavoritesWorker(), TripWorker()]
    loop = asyncio.get_event_loop()

    def shutdown():
        for worker in workers:
            worker.stop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown)
    except NotImplementedError:
        pass
    try:
        await asyncio.gather(*[worker.run() for worker in workers])
    except KeyboardInterrupt:
        shutdown()
if __name__ == '__main__':
    asyncio.run(main())

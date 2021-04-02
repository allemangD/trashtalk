import asyncio
import datetime
import logging
import typing

import humanize


async def sleep(delta: typing.Union[datetime.timedelta, float] = None, **args):
    """Try to interpret delta as a timedelta or float number of seconds;
    or use keyword arguments to construct a timedelta.

    returns True if sleeping occurred
    """

    if delta is None:
        delta = datetime.timedelta(**args)

    try:
        msg = humanize.precisedelta(delta)
        delay = delta.total_seconds()
    except AttributeError:
        msg = f'{delta:.2f}s'
        delay = delta  # assume delta is already a number

    if delay > 0:
        logging.getLogger('util').info('sleeping %s', msg)
        await asyncio.sleep(delay)
        return True

    return False
import asyncio
import logging
import time

import httpx

BASE_URL = 'https://statsapi.web.nhl.com/api/v1/'
CLIENT = httpx.AsyncClient(base_url=BASE_URL)


class Bundle(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def rate_limit(delay):
    def dec(func):
        last_call = 0

        async def wrap(*a, **kw):
            nonlocal last_call

            now = time.monotonic()
            wait = last_call + delay - now

            if wait > 0:
                await asyncio.sleep(wait)

            result = await func(*a, **kw)
            last_call = now
            return result

        return wrap

    return dec


# @rate_limit(delay=10)
async def get(path, *params, **query):
    logging.debug('GET api %r %r %r', path, params, query)

    async with CLIENT:
        query = {k: v for k, v in query.items() if v is not None}
        resp = await CLIENT.get(path.format(*params), params=query)
        return resp.json(object_hook=Bundle)


async def schedule(team_id=None, start_date=None, end_date=None):
    data = await get('schedule', teamId=team_id, startDate=start_date, endDate=end_date)
    return [game for date in data.dates for game in date.games]


async def live_games(team_id=None, start_date=None, end_date=None):
    games = await schedule(team_id=team_id, start_date=start_date, end_date=end_date)
    return [game for game in games if game.status.abstractGameState == 'Live']

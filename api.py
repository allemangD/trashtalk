import datetime
import logging

import httpx

import util

BASE_URL = 'https://statsapi.web.nhl.com/api/v1/'
CLIENT = httpx.AsyncClient(base_url=BASE_URL)

log = logging.getLogger('trash.api')

DELAY = datetime.timedelta(seconds=10)


class Bundle(dict):
    """Convenience class to access API results with . operator without needing
     to fully wrap the API"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


async def get(path, *params, **query):
    """Make a GET request to the NHL API"""

    log.debug('GET api %r %r %r', path, params, query)

    async with CLIENT:
        query = {k: v for k, v in query.items() if v is not None}
        resp = await CLIENT.get(path.format(*params), params=query)
        return resp.json(object_hook=Bundle)


async def schedule(team_id=None, start_date=None, end_date=None):
    """Get a list of scheduled (or historical) games from the NHL API"""

    data = await get('schedule', teamId=team_id, startDate=start_date, endDate=end_date)
    return [game for date in data.dates for game in date.games]


async def live_games(team_id=None, start_date=None, end_date=None):
    """Filter results from schedule to only contain live games"""

    games = await schedule(team_id=team_id, start_date=start_date, end_date=end_date)
    return [game for game in games if game.status.abstractGameState == 'Live']


async def next_game(team_id, states=('Preview', 'Live'), days=7):
    """Get the first game from today to `days` days from today, where team_id is
     playing, whose state is in `states`"""

    today = datetime.date.today()
    start = today - datetime.timedelta(days=1)
    end = today + datetime.timedelta(days=days)

    games = await schedule(team_id=team_id, start_date=start, end_date=end)
    log.info('found %s games', len(games))
    for game in games:
        log.debug('game %s: %s (%s)', game.gamePk, game.status.abstractGameState, game.status.detailedState)
        if game.status.abstractGameState in states:
            return game
    return None


class PlaySequence:
    """
    Responsible for iterating through each play of a game exactly once.

    Use a marker to keep track of how many plays have already been seen. On each API call,
    only yield the plays which occurred after the marker, then update the marker.

    Instances are iterable, and will yield each play of a game exactly once,
    in realtime, until the game is finalized.

    If skip() is called, any new plays will be discarded.
    """

    log = logging.getLogger('trash.api.plays')

    def __init__(self, game_id):
        self.game_id = game_id
        self.marker = 0

        self.final = False

    @staticmethod
    def _final_play(data):
        """Since the API does not generate a play for a game being finalized, generate one manually.

        We want data summarizing the game; we fetch this from the finalized game lineScore.
        """

        home = data.liveData.linescore.teams.home
        away = data.liveData.linescore.teams.away

        winner, loser = (home, away) if home.goals > away.goals else (away, home)

        desc = f'{winner.team.name} beat {loser.team.name} {winner.goals} to {loser.goals}'

        return Bundle({
            'result': Bundle({
                'event': 'Final',
                'eventCode': '-',
                'eventTypeId': 'FINAL',
                'description': desc,
            }),
            'team': winner.team,
            'about': Bundle({
                'home': home,
                'away': away
            })
        })

    async def _fetch(self):
        """yield one batch of new plays. If the game is Final, also yield a final_play."""

        data = await get('game/{}/feed/live', self.game_id)
        all_plays = data.liveData.plays.allPlays
        self.log.debug('received %s plays', len(all_plays))
        new_plays = all_plays[self.marker:]
        self.log.info('received %s new plays', len(new_plays))
        self.marker = len(all_plays)

        self.final = data.gameData.status.abstractGameState == 'Final'

        for play in new_plays:
            yield play

        if self.final:
            yield self._final_play(data)

    async def skip(self):
        """Discard all new plays"""

        plays = [e async for e in self._fetch()]
        self.log.info('skipping %s plays', len(plays))

    async def __aiter__(self):
        """Yield plays until the game is finalized."""

        while not self.final:
            async for play in self._fetch():
                yield play

            await util.sleep(DELAY)

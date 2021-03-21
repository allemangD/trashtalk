import logging
import random

import api
from api import Bundle


class EventSequence:
    def __init__(self, game_id):
        self.game_id = game_id
        self.marker = 0

        self.final = False

    def final_play(self, data):
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

    async def fetch(self):
        data = await api.get('game/{}/feed/live', self.game_id)
        all_plays = data.liveData.plays.allPlays
        new_plays = all_plays[self.marker:]
        self.marker = len(all_plays)

        self.final = data.gameData.status.abstractGameState == 'Final'

        for play in new_plays:
            yield play

        if self.final:
            yield self.final_play(data)

    async def skip(self):
        async for play in self.fetch():
            pass

    async def __aiter__(self):
        while not self.final:
            async for play in self.fetch():
                yield play


def load(f):
    for line in f:
        mask, _, fmt = line.strip().partition(':')
        yield mask, fmt


class Messager:
    def __init__(self, path):
        self.messages = list(load(open(path)))

    def get(self, event):
        options = [fmt for mask, fmt in self.messages if event.startswith(mask)]
        if not options:
            return None

        return random.choice(options)


class Preprocessor:
    def __init__(self, game, focus_id):
        self.game = game
        self.focus_id = focus_id

        self.teams = self.game.teams
        home, away = self.teams.home.team, self.teams.away.team
        self.is_home = home.id == focus_id
        self.teams.focus, self.teams.other = (home, away) if self.is_home else (away, home)

    def preprocess(self, play):
        event = play.result.eventTypeId
        descr = play.result.description

        if 'team' in play:
            sub = 'focus' if play.team.id == self.focus_id else 'other'
            event = f'{event}.{sub}'

        if 'players' in play:
            play.players = Bundle({
                item.playerType: item.player
                for item in play.players
            })

        play.teams = self.teams

        logging.debug('%s: %s', event, descr)
        return event, play


async def message_sequence(game, focus_id, messager, skip=False):
    seq = EventSequence(game.gamePk)
    proc = Preprocessor(game, focus_id)

    if skip:
        await seq.skip()

    async for play in seq:
        event, play = proc.preprocess(play)
        fmt = messager.get(event)
        if not fmt:
            continue

        text = fmt.format(fmt, event=event, play=play, game=game)
        logging.info('%s: %r', event, text)
        yield text

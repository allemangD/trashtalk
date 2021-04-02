import logging
import random

import api


class PatternLookup:
    """Responsible for getting a random message matching a given event."""

    log = logging.getLogger('trash.pattern')

    @classmethod
    def load(cls, file):
        for line in file:
            mask, _, val = line.strip().partition(':')
            yield mask, val

    def __init__(self, file):
        self.patterns = list(self.load(file))

        self.log.info('loaded %s patterns', len(self.patterns))

    def get(self, key):
        options = [val for mask, val in self.patterns if key.startswith(mask)]

        if not options:
            self.log.debug('found no options for key %r', key)
            return None
        else:
            self.log.info('found %s options for key %r', len(options), key)

        result = random.choice(options)
        self.log.debug('result for key %r: %r', key, result)

        return result


class Transformer:
    """Responsible for adding "focus" and "other" team references to play data."""

    log = logging.getLogger('trash.transform')

    def __init__(self, game, focus_id):
        self.game = game
        self.focus_id = focus_id

        self.teams = self.game.teams
        home, away = self.teams.home.team, self.teams.away.team
        self.is_home = home.id == focus_id
        self.teams.focus, self.teams.other = (home, away) if self.is_home else (away, home)

    def __call__(self, play):
        event = play.result.eventTypeId
        descr = play.result.description

        self.log.debug('received play %s: %s', event, descr)

        if 'team' in play:
            sub = 'focus' if play.team.id == self.focus_id else 'other'
            event = f'{event}.{sub}'

        if 'players' in play:
            play.players = api.Bundle({
                item.playerType: item.player
                for item in play.players
            })

        play.teams = self.teams

        self.log.debug('added focus data to play %s', event)

        return event, play


async def watch(game, focus_id, patterns_file, send, skip):
    log = logging.getLogger('trash.watch')

    patterns = PatternLookup(patterns_file)
    transform = Transformer(game, focus_id)

    plays = api.PlaySequence(game.gamePk)

    if skip:
        await plays.skip()

    async for play in plays:
        event, play = transform(play)
        log.debug('%s: %s', event, play.result.description)

        fmt = patterns.get(event)
        if not fmt:
            continue

        text = fmt.format(event=event, play=play, game=game)
        log.info('%s: %s', event, text)
        await send(text)

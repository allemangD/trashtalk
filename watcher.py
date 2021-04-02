import logging
import random

import api


class PatternLookup:
    """
    Responsible for getting a random message matching a given event.

    keep a list of (key, value) pairs, where key is a prefix to specific events

    for example a key 'A.B' could be matched by events 'A.B', 'A.B.C', 'A.B.D', etc. but _not_ by 'A'

    if multiple entries are matched, choose one at random.
    """

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
    """
    Responsible for adding "focus" and "other" team references to play data.

    The data given by the api only deals with teams "home" and "away". For this bot
     it is useful to track the "focus" team and the "other" team.

    This class aliases `game.teams.home` and `game.teams.away` by `game.teams.focus`
     and `game.teams.other`, depending on whether the focused team is home or away.

    It also generates sub-events for events which have an associated team (goals,
     shots, etc). If the play team is the focused team, then the sub-event is
     `<EVENT>.focus`, and similarly with `<EVENT>.other`.

    Finally, the `players` entry in play data is poorly formatted for str.format.
    For example, a goal api response might contain a players list:

    [
      { playerType: Scorer, ... },
      { playerType: Goalie, ... },
    ]

    This is transformed to a dictionary, better suited for str.format:

    {
      Scorer: {...},
      Goalie: {...},
    }
    """

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

        # create sub-event if play has associated team
        if 'team' in play:
            sub = 'focus' if play.team.id == self.focus_id else 'other'
            event = f'{event}.{sub}'

        # map players list to dict, if present
        if 'players' in play:
            play.players = api.Bundle({
                item.playerType: item.player
                for item in play.players
            })

        play.teams = self.teams

        self.log.debug('added focus data to play %s', event)

        return event, play


async def watch(game, focus_id, patterns_file, send, skip):
    """
    React to all plays of a game, in realtime, until the game status is final.

    Use a PatternLookup to match play events with message patterns, and format
    this with data supplied by the API and augmented by a Transformer.

    If no pattern is found, skip that play.

    Send the resulting message via the send callback.

    If skip is true, skip any plays which have already occurred when the
    function is called.

    """

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

import datetime
import logging
import os

import discord
from dateutil import parser, tz

import api
import util
import watcher


def envbool(e):
    return e.lower() not in ('false', 'no', 'off', '0')


DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
DISCORD_CHANNEL = int(os.environ['DISCORD_CHANNEL'])
DRY_RUN = envbool(os.environ.get('DRY_RUN', 'true'))

FOCUS_TEAM_ID = int(os.environ['FOCUS_TEAM_ID'])
PATTERNS_FILE = os.environ['PATTERNS_FILE']

SKIP_CURRENT = envbool(os.environ.get('SKIP_CURRENT', 'true'))

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s:%(name)-16s: %(message)s',
    level='WARNING',
    datefmt='%Y-%m-%d %H:%M:%S',
)

logging.getLogger('trash').setLevel('INFO')
logging.getLogger('trash.main').setLevel('DEBUG')
logging.getLogger('trash.watch').setLevel('DEBUG')
logging.getLogger('trash.api.plays').setLevel('DEBUG')

log = logging.getLogger('trash.main')

dcli = discord.Client()


@dcli.event
async def on_ready():
    channel: discord.TextChannel = dcli.get_channel(DISCORD_CHANNEL)

    if not DRY_RUN:
        send = channel.send
    else:
        _dry = logging.getLogger('trash.dry')

        async def send(text):
            _dry.info(text)

    while True:
        game = await api.next_game(FOCUS_TEAM_ID)
        if not game:
            log.warning('could not find a live or scheduled game.')
            await util.sleep(days=1)
            continue

        title = f'{game.teams.home.team.name} vs. {game.teams.away.team.name}'

        date = parser.parse(game.gameDate)
        utcnow = datetime.datetime.now(tz.tzutc())

        delay = date - utcnow - datetime.timedelta(seconds=30)
        log.info('waiting for game %s (%s)', game.gamePk, title)

        in_progress = not await util.sleep(delay)
        log.info('watching game %s (%s)', game.gamePk, title)

        if in_progress and SKIP_CURRENT:
            log.debug('not notifying because game is already in progress')
        else:
            await send(f'watching {title}')

        await watcher.watch(
            game=game,
            focus_id=FOCUS_TEAM_ID,
            patterns_file=open(PATTERNS_FILE),
            send=send,
            skip=SKIP_CURRENT
        )


if __name__ == '__main__':
    dcli.run(DISCORD_TOKEN)

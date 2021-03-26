import asyncio
import datetime
import logging
import os

import discord
import humanize
from dateutil import parser
from dateutil import tz

import api
import processor

DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
DISCORD_CHANNEL = int(os.environ['DISCORD_CHANNEL'])
FOCUS_TEAM_ID = int(os.environ['FOCUS_TEAM_ID'])

logging.basicConfig(level='DEBUG')
logging.getLogger('discord').setLevel('WARNING')

dcli = discord.Client()


async def next_game(states=('Preview', 'Live'), days=7):
    today = datetime.date.today()
    start = today - datetime.timedelta(days=1)
    end = today + datetime.timedelta(days=days)

    schedule = await api.schedule(team_id=FOCUS_TEAM_ID, start_date=start, end_date=end)
    logging.info('found %s games', len(schedule))
    for game in schedule:
        logging.debug('game %s: %s (%s)', game.gamePk, game.status.abstractGameState, game.status.detailedState)
        if game.status.abstractGameState in states:
            return game
    return None


@dcli.event
async def on_ready():
    channel: discord.TextChannel = dcli.get_channel(DISCORD_CHANNEL)

    logging.info('started')
    while True:
        game = await next_game()
        if not game:
            logging.warning('could not find a live or scheduled game. waiting one day and trying again.')
            await asyncio.sleep(datetime.timedelta(days=1).total_seconds())
            continue

        title = f'{game.teams.home.team.name} vs. {game.teams.away.team.name}'

        date = parser.parse(game.gameDate)
        utcnow = datetime.datetime.now(tz.tzutc())
        delay = date - utcnow

        logging.info('waiting for game %s (%s)', game.gamePk, title)

        wait = delay.total_seconds() - 30  # start working before game start
        if wait > 0:
            delta = humanize.precisedelta(delay)
            logging.info('waiting %s (%.fs)', delta, wait)
            await asyncio.sleep(wait)

        logging.info('watching %r', title)
        await channel.send(f'watching {title}')

        messager = processor.Messager('patterns/goals.txt')
        sequence = processor.message_sequence(game, FOCUS_TEAM_ID, messager, skip=True)

        async for message in sequence:
            await channel.send(message)

        logging.info('game over')


dcli.run(DISCORD_TOKEN)

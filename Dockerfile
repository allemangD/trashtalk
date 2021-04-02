FROM python:3-alpine

RUN apk add build-base

RUN pip install -U pip

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY / .

ENV DISCORD_TOKEN=''
ENV DISCORD_CHANNEL=''
ENV DRY_RUN='false'

ENV FOCUS_TEAM_ID='12'
ENV PATTERNS_FILE='patterns/goals.txt'

ENV SKIP_CURRENT='true'

CMD ["python3", "main.py"]

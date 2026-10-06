#!/bin/zsh
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Run the setup steps in README.md first.'
  exit 1
fi
(
  sleep 2
  open http://127.0.0.1:5000
) &
exec .venv/bin/python -m flask --app wsgi run --host 127.0.0.1 --port 5000

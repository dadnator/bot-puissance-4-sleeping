from flask import Flask
from threading import Thread

app = Flask('')


@app.route('/')
def home():
  return "le bot est en ligne jeux de puissance 4 sleeping !"


def run():
  app.run(host='0.0.0.0', port=8095)


def keep_alive():
  t = Thread(target=run)
  t.start()

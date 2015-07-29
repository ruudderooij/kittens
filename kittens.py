from collections import namedtuple
from concurrent import futures
import json
import random
import time

import prometheus_client

from tornado import gen
from tornado import httpserver
from tornado import ioloop
from tornado import web

# -----------------------------------------------------------------------------

Kitten = namedtuple('Kitten', ['filename', 'description'])

class KittenFactory(object):

    def __init__(self):
        self.kittens = []
        for data in json.load(open('kittens.json')):
            self.kittens.append(Kitten(filename=data['filename'], description=data['description']))

    def get_kitten(self):
        return random.choice(self.kittens)

# -----------------------------------------------------------------------------

class InstrumentedHandler(web.RequestHandler):
    duration_metric = prometheus_client.Summary('http_request_duration_microseconds', 'The HTTP request latencies in microseconds.', ['handler'])
    status_metric = prometheus_client.Counter('http_requests_total', 'Total number of HTTP requests made.', ['code'])

    def handler(self):
        # TODO: this is super hacky.
        return str(self.__class__).split("'")[1].split('.')[1]

    def on_finish(self):
        super(InstrumentedHandler, self).on_finish()
        self.duration_metric.labels(self.handler()).observe(self.request.request_time() * 1e6)
        self.status_metric.labels(self.get_status()).inc()

# -----------------------------------------------------------------------------

# I'm simultaneously amazed and appalled that this actually works.
class InstrumentedStaticHandler(InstrumentedHandler, web.StaticFileHandler):
    pass

class MainHandler(InstrumentedHandler):
    def initialize(self, kitten_factory):
        self.kitten_factory = kitten_factory

    def get(self):
        kitten = self.kitten_factory.get_kitten()
        self.render('index.html',
                filename=self.static_url(kitten.filename),
                description=kitten.description)

class MetricsHandler(InstrumentedHandler):
    def get(self):
        self.set_header("Content-Type", "text/plain")
        self.write('# REMOTE IP: {}\n\n'.format(self.request.remote_ip))
        self.write(prometheus_client.generate_latest())

application = web.Application([
        (r"/", MainHandler, dict(kitten_factory=KittenFactory())),
        (r"/metrics", MetricsHandler),
    ],
    static_path="static",
    static_handler_class=InstrumentedStaticHandler,
    template_path="templates")

if __name__ == "__main__":
    prometheus_client.start_http_server(8000)
    server = httpserver.HTTPServer(application, xheaders=True)
    server.listen(8888)
    ioloop.IOLoop.current().start()

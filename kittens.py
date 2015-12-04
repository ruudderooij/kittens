from collections import namedtuple
from concurrent import futures
import ipaddress
import logging
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
    total_metric = prometheus_client.Counter('http_requests_total', 'Total number of HTTP requests made.', ['code', 'handler', 'method'])

    def on_finish(self):
        super(InstrumentedHandler, self).on_finish()
        handler = type(self).__name__
        self.duration_metric.labels(handler).observe(self.request.request_time() * 1e6)
        self.total_metric.labels(self.get_status(), handler, self.request.method.lower()).inc()

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
        if not ipaddress.ip_address(self.request.remote_ip).is_private:
            self.set_status(403)
            return
        self.set_header('Content-Type', prometheus_client.CONTENT_TYPE_LATEST)
        self.write(prometheus_client.generate_latest())

# -----------------------------------------------------------------------------

application = web.Application([
        (r'/', MainHandler, dict(kitten_factory=KittenFactory())),
        (r'/metrics', MetricsHandler),
    ],
    static_path='static',
    static_handler_class=InstrumentedStaticHandler,
    template_path='templates')

if __name__ == '__main__':
    logging.getLogger('tornado.access').setLevel(logging.INFO)
    server = httpserver.HTTPServer(application, xheaders=True)
    server.listen(8888)
    ioloop.IOLoop.current().start()

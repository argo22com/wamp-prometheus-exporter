import os

from autobahn.twisted.component import Component, run
from autobahn.twisted.wamp import Session
from prometheus_client import Gauge
from prometheus_client.twisted import MetricsResource
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.web.resource import Resource
from twisted.web.server import Site

g_active_sessions = Gauge('active_sessions', 'Number of sessions currently active', ['router_url', 'realm'])
g_registration_callees = Gauge('active_callees', 'Number of sessions currently attached to the registration',
                               ['router_url', 'realm', 'uri'])

settings = {
    "wamp_url": os.environ.get('WAMP_URL'),
    "wamp_realm": os.environ.get('WAMP_REALM'),
    "wamp_principal": os.environ.get('WAMP_PRINCIPAL'),
    "wamp_ticket": os.environ.get('WAMP_TICKET'),
}
component = Component(
    transports=settings.get('wamp_url'),
    realm=settings.get('wamp_realm'),
    authentication={
        "ticket": {
            "authid": settings.get('wamp_principal'),
            "ticket": settings.get('wamp_ticket'),
        }
    }
)

meta = {
    "session": None,
    "session_details": None,
}


def update_session_count():
    session_count = yield meta["session"].call("wamp.session.count")
    g_active_sessions.labels(settings.get('wamp_url'), settings.get('wamp_realm')).set(session_count)


@component.on_join
@inlineCallbacks
def joined(session: Session, details):
    meta['session_details'] = details
    meta["session"] = session
    yield from update_session_count()

    rpc_list = yield meta['session'].call('wamp.registration.list')
    for id in rpc_list['exact']:
        info = yield meta['session'].call('wamp.registration.get', id)
        print(info)
        callees = yield meta['session'].call('wamp.registration.count_callees', id)
        g_registration_callees.labels(settings.get('wamp_url'), settings.get('wamp_realm'), info['uri']).set(callees)


@component.subscribe('wamp.session.on_join')
@inlineCallbacks
def on_join(*args, **kwargs):
    yield from update_session_count()


@component.subscribe('wamp.session.on_leave')
@inlineCallbacks
def on_leave(*args, **kwargs):
    yield from update_session_count()


@component.subscribe('wamp.registration.on_register')
# @inlineCallbacks
def on_register(*args, **kwargs):
    session_id, rpc_id = args
    print('on_register')
    print(args)
    print(kwargs)


@component.subscribe('wamp.registration.on_unregister')
@inlineCallbacks
def on_unregister(*args, **kwargs):
    session_id, rpc_id = args
    # info = yield meta['session'].call('wamp.registration.get', rpc_id)  # fails when this is was last callee
    print('on_unregister')
    # print(info)
    print(args)
    print(kwargs)


@component.subscribe('wamp.registration.on_create')
# @inlineCallbacks
def on_registration_create(*args, **kwargs):
    session_id, rpc_info = args
    print('on_create')
    print(args)
    print(kwargs)


@component.subscribe('wamp.registration.on_delete')
# @inlineCallbacks
def on_registration_delete(*args, **kwargs):
    session_id, rpc_id = args
    print('on_delete')
    print(args)
    print(kwargs)


@component.on_leave
# @inlineCallbacks
def left(session, details):
    print("session closed")


@component.on_connect
# @inlineCallbacks
def connected(session, details):
    print("connected")


if __name__ == "__main__":
    root = Resource()
    root.putChild(b'metrics', MetricsResource())

    factory = Site(root)

    reactor.listenTCP(8000, factory)
    run([component])

import os

from autobahn.twisted.component import Component, run
from autobahn.twisted.wamp import Session
from prometheus_client import Gauge
from prometheus_client.twisted import MetricsResource
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.web.resource import Resource
from twisted.web.server import Site

g_active_sessions = Gauge('active_session_count', 'Number of sessions currently active', ['router_url', 'realm'])

g_registration_callees = Gauge('active_callee_count', 'Number of sessions currently attached to the registration',
                               ['router_url', 'realm', 'uri'])

g_subscription_subscribers = Gauge('active_subscription_count',
                                   'Number of sessions currently subscribed to the subscription',
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
    "registrations": {},
    "subscriptions": {},
}


def update_session_count():
    session_count = yield meta["session"].call("wamp.session.count")
    g_active_sessions.labels(settings.get('wamp_url'), settings.get('wamp_realm')).set(session_count)


def init_registration_callee_count():
    rpc_list = yield meta['session'].call('wamp.registration.list')
    for id in rpc_list['exact']:
        yield from create_registration_callee(id)


def create_registration_callee(id):
    info = yield meta['session'].call('wamp.registration.get', id)
    meta['registrations'][id] = info['uri']
    yield from update_registration_callee_count(id)


def remove_registration_callee(id):
    uri = meta['registrations'].get(id, None)
    if uri:
        del meta['registrations'][id]
        try:
            g_registration_callees.remove(
                settings.get('wamp_url'),
                settings.get('wamp_realm'),
                uri
            )
        except:
            pass


def update_registration_callee_count(id):
    uri = meta['registrations'].get(id)
    if not uri:
        return  # registration right after create, count will be updated by create
    try:
        callees = yield meta['session'].call('wamp.registration.count_callees', id)
        g_registration_callees.labels(
            settings.get('wamp_url'),
            settings.get('wamp_realm'),
            uri
        ).set(callees)

    except:
        remove_registration_callee(id)


def init_subscription_subscriber_count():
    rpc_list = yield meta['session'].call('wamp.subscription.list')
    for id in rpc_list['exact']:
        yield from create_subscription(id)


def create_subscription(id):
    info = yield meta['session'].call('wamp.subscription.get', id)
    meta['subscriptions'][id] = info['uri']
    yield from update_subscription_subscriber_count(id)


def remove_subscription(id):
    uri = meta['subscriptions'].get(id, None)
    if uri:
        del meta['subscriptions'][id]
        try:
            g_subscription_subscribers.remove(
                settings.get('wamp_url'),
                settings.get('wamp_realm'),
                uri
            )
        except:
            pass


def update_subscription_subscriber_count(id):
    uri = meta['subscriptions'].get(id)
    if not uri:
        return  # subscription right after create, count will be updated by create
    try:
        subscribers = yield meta['session'].call('wamp.subscription.count_subscribers', id)
        g_subscription_subscribers.labels(
            settings.get('wamp_url'),
            settings.get('wamp_realm'),
            uri
        ).set(subscribers)
    except:
        remove_subscription(id)


"""
lifecycle callbacks
"""


@component.on_join
@inlineCallbacks
def joined(session: Session, details):
    meta['session_details'] = details
    meta["session"] = session
    yield from update_session_count()
    yield from init_registration_callee_count()
    yield from init_subscription_subscriber_count()


@component.subscribe('wamp.session.on_join')
@inlineCallbacks
def on_join(*args, **kwargs):
    yield from update_session_count()


@component.subscribe('wamp.session.on_leave')
@inlineCallbacks
def on_leave(*args, **kwargs):
    yield from update_session_count()


@component.on_leave
# @inlineCallbacks
def left(session, details):
    print("session closed")


@component.on_connect
# @inlineCallbacks
def connected(session, details):
    print("connected")


"""
RPC
"""


@component.subscribe('wamp.registration.on_create')
@inlineCallbacks
def on_registration_create(session_id, info, **kwargs):
    yield from create_registration_callee(info.get('id'))


@component.subscribe('wamp.registration.on_register')
@inlineCallbacks
def on_registration_register(session_id, registration_id, **kwargs):
    yield from update_registration_callee_count(registration_id)


@component.subscribe('wamp.registration.on_unregister')
@inlineCallbacks
def on_registration_unregister(session_id, registration_id, **kwargs):
    yield from update_registration_callee_count(registration_id)


@component.subscribe('wamp.registration.on_delete')
@inlineCallbacks
def on_registration_delete(session_id, registration_id, **kwargs):
    yield from update_registration_callee_count(registration_id)


"""
Pub/Sub
"""


@component.subscribe('wamp.subscription.on_create')
@inlineCallbacks
def on_subscription_create(session_id, info, **kwargs):
    yield from create_subscription(info.get('id'))


@component.subscribe('wamp.subscription.on_subscribe')
@inlineCallbacks
def on_subscription_subscribe(session_id, subscription_id, **kwargs):
    yield from update_subscription_subscriber_count(subscription_id)


@component.subscribe('wamp.subscription.on_unsubscribe')
@inlineCallbacks
def on_subscription_unsubscribe(session_id, subscription_id, **kwargs):
    yield from update_subscription_subscriber_count(subscription_id)


@component.subscribe('wamp.subscription.on_delete')
@inlineCallbacks
def on_subscription_delete(session_id, subscription_id, **kwargs):
    yield from update_subscription_subscriber_count(subscription_id)


if __name__ == "__main__":
    root = Resource()
    root.putChild(b'metrics', MetricsResource())

    factory = Site(root)

    reactor.listenTCP(9123, factory)
    run([component])

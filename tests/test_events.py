from __future__ import annotations

import asyncio

from radui.transport import EventBroker


def test_event_broker_replays_events_after_last_event_id():
    broker = EventBroker(history_size=4)
    broker.publish("s1", "invalidate", {"component_ids": ["a"]})
    broker.publish("s1", "invalidate", {"component_ids": ["b"]})

    async def read_two():
        stream = broker.stream("s1", last_event_id=1)
        first = await anext(stream)
        await stream.aclose()
        return first

    event = asyncio.run(read_two())
    assert "id: 2" in event
    assert '"component_ids":["b"]' in event


def test_event_broker_requests_reset_when_replay_history_has_a_gap():
    broker = EventBroker(history_size=2)
    for index in range(4):
        broker.publish("s1", "invalidate", {"index": index})

    async def read_reset():
        stream = broker.stream("s1", last_event_id=0)
        event = await anext(stream)
        await stream.aclose()
        return event

    event = asyncio.run(read_reset())
    assert "event: reset" in event


def test_event_broker_does_not_replay_old_events_on_fresh_subscription():
    broker = EventBroker()
    broker.publish("s1", "invalidate", {"old": True})

    async def read_live():
        stream = broker.stream("s1", last_event_id=None, keepalive_seconds=0.001)
        event = await anext(stream)
        await stream.aclose()
        return event

    event = asyncio.run(read_live())
    assert event == ": keep-alive\n\n"


def test_event_broker_forgets_session_after_subscribers_close():
    broker = EventBroker()
    broker.publish("s1", "invalidate", {})
    broker.forget_session("s1")
    assert broker.current_sequence("s1") == 0


def test_event_broker_can_publish_from_a_different_thread():
    broker = EventBroker()

    async def run():
        stream = broker.stream("thread-session", last_event_id=None, keepalive_seconds=1)
        waiter = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        await asyncio.to_thread(broker.publish, "thread-session", "invalidate", {"view_id": "/"})
        event = await asyncio.wait_for(waiter, timeout=1)
        await stream.aclose()
        return event

    event = asyncio.run(run())
    assert "event: invalidate" in event
    assert '"view_id":"/"' in event



def test_event_broker_requests_reset_when_cursor_is_from_newer_timeline():
    broker = EventBroker()
    # Simulate a browser reconnecting with a Last-Event-ID retained from before
    # an application restart cleared the process-local event sequence.
    async def read_reset():
        stream = broker.stream("s1", last_event_id=19)
        event = await anext(stream)
        await stream.aclose()
        return event

    event = asyncio.run(read_reset())
    assert "event: reset" in event

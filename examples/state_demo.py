"""Demonstrate RADUI 0.4 scoped state and dependency tracking.

This is a runtime API demonstration, not an HTTP session implementation.
The host supplies authenticated user and session identifiers.
"""

import radui as gx

app = gx.App("RADUI State Demo", app_id="state-demo")

counter = gx.state("counter.value", 0, scope="session")
user_theme = gx.state("preferences.theme", "system", scope="user")
maintenance = gx.state("maintenance.enabled", False, scope="app")

# The host must supply a trusted session ID. In a real application, this comes
# from a server-verified session mechanism, not an arbitrary query parameter.
alice_tab = app.state_context(
    session_id="session-alice",
    user_id="alice",
    view_id="dashboard",
)
alice_second_tab = app.state_context(
    session_id="session-alice",
    user_id="alice",
    view_id="settings",
)
bob_tab = app.state_context(
    session_id="session-bob",
    user_id="bob",
    view_id="dashboard",
)

with alice_tab.activate():
    counter.value = 4
    user_theme.value = "dark"

with alice_second_tab.activate():
    assert user_theme.value == "dark"  # User scope is shared across Alice's tabs.
    assert counter.value == 4  # Session scope is shared across Alice's tabs.

with bob_tab.activate():
    assert user_theme.value == "system"  # Different user.
    assert counter.value == 0  # Different session.

# A component render records the state it reads. Later writes return the exact
# contexts/components that need to be reconsidered by a future renderer.
with alice_tab.track_component("counter-label"):
    _ = counter.value

change = alice_tab.write(counter, 5)
print("Changed:", change.changed)
print("Revision:", change.revision)
print("Invalidations:", change.invalidations)

# An app-scoped change is visible across all contexts.
alice_tab.write(maintenance, True)
with bob_tab.activate():
    assert maintenance.value is True

print("RADUI State demo passed")

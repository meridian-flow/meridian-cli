from pathlib import Path

import pytest

from meridian.lib.chat.backend_acquisition import ColdSpawnAcquisition
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import ConnectionCapabilities, ConnectionConfig
from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.launch_spec import ClaudeLaunchSpec
from meridian.lib.safety.permissions import UnsafeNoOpPermissionResolver
from meridian.lib.streaming.drain_policy import PersistentDrainPolicy


class Connection:
    harness_id = HarnessId.CLAUDE
    spawn_id = SpawnId("s1")
    session_id = None
    subprocess_pid = None
    capabilities = ConnectionCapabilities(
        mid_turn_injection="queue",
        supports_steer=False,
        supports_cancel=True,
        runtime_model_switch=False,
        structured_reasoning=True,
    )

    def health(self):
        return True

    async def send_user_message(self, text):
        pass

    async def send_cancel(self):
        pass

    async def stop(self):
        pass

    async def events(self):
        if False:
            yield None


class SpawnManager:
    def __init__(self):
        self.calls = []
        self.connection = Connection()
        self.drain_policy = None
        self.started_config = None

    def register_observer(self, spawn_id, observer):
        self.calls.append(("register", spawn_id, observer))

    async def start_spawn(self, config, spec, *, drain_policy=None, on_event=None):
        self.calls.append(("start", config.spawn_id, spec))
        self.started_config = config
        self.drain_policy = drain_policy
        return self.connection

    async def start_heartbeat(self, spawn_id):
        self.calls.append(("heartbeat", spawn_id, None))


class Normalizer:
    def normalize(self, event):
        return []

    def reset(self):
        pass


class Pipeline:
    async def ingest(self, event):
        pass

    async def on_execution_complete(self, generation=None):
        pass


@pytest.mark.asyncio
async def test_cold_acquisition_registers_observer_before_start_and_uses_persistent_policy(
    tmp_path: Path,
):
    manager = SpawnManager()
    spawn_id = SpawnId("s-chat")

    acquisition = ColdSpawnAcquisition(
        spawn_manager=manager,
        normalizer_factory=lambda harness_id: Normalizer(),
        pipeline_factory=lambda chat_id: Pipeline(),
        connection_config_factory=lambda chat_id, prompt: ConnectionConfig(
            spawn_id=spawn_id,
            harness_id=HarnessId.CLAUDE,
            prompt=prompt,
            project_root=tmp_path,
            env_overrides={},
        ),
        launch_spec_factory=lambda prompt: ClaudeLaunchSpec(
            prompt=prompt,
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        ),
    )

    handle = await acquisition.acquire("c1", "hello")

    assert [call[0] for call in manager.calls] == ["register", "start", "heartbeat"]
    assert manager.started_config.prompt == "hello"
    assert isinstance(manager.drain_policy, PersistentDrainPolicy)
    assert handle.spawn_id == spawn_id

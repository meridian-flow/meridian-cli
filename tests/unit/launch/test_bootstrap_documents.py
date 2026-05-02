from types import SimpleNamespace

from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch import LaunchRequest, launch_primary
from meridian.lib.launch import context as launch_context


def test_launch_primary_loads_bootstrap_docs_from_launch_project_root(tmp_path, monkeypatch):
    project_root = tmp_path / 'project'
    (project_root / '.meridian').mkdir(parents=True)
    (project_root / 'mars.toml').write_text('[settings]\ntargets=[".agents"]\n', encoding='utf-8')
    doc_dir = project_root / '.mars' / 'bootstrap' / 'setup'
    doc_dir.mkdir(parents=True)
    (doc_dir / 'BOOTSTRAP.md').write_text('setup docs', encoding='utf-8')

    captured = {}

    def fake_build_launch_context(**kwargs):
        captured['request'] = kwargs['request']
        return SimpleNamespace(warnings=(), argv=('fake-harness',))

    monkeypatch.setattr(launch_context, 'build_launch_context', fake_build_launch_context)

    result = launch_primary(
        project_root=project_root,
        request=LaunchRequest(dry_run=True, include_bootstrap_documents=True),
        harness_registry=get_default_harness_registry(),
    )

    assert result.command == ('fake-harness',)
    docs = captured['request'].supplemental_prompt_documents
    assert [(doc.kind, doc.logical_name) for doc in docs] == [('bootstrap', 'setup')]
    assert docs[0].content == '# Bootstrap: setup (package)\n\nsetup docs'

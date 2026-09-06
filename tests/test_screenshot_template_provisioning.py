import importlib.util
from pathlib import Path


SCRIPT = Path("scripts/provision_screenshot_template.py")


def _module():
    spec = importlib.util.spec_from_file_location("template_provision", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_template_guard_rejects_expert_sections_and_secrets(tmp_path):
    module = _module()
    template = tmp_path / "unsafe.tpl"
    template.write_text("<chart>\n<expert>\nadmin_token=secret\n", encoding="utf-8")
    try:
        module.validate_template(template)
    except ValueError as exc:
        assert "forbidden marker" in str(exc)
    else:
        raise AssertionError("secret-bearing template must be rejected")


def test_template_guard_copies_only_a_sanitized_tpl(tmp_path):
    module = _module()
    source = tmp_path / "approved.tpl"
    source.write_text("<chart>\nsymbol=US100\n</chart>\n", encoding="utf-8")
    destination = module.provision(source, tmp_path / "Profiles" / "Templates")
    assert destination.name == "NEXUS_Screenshot.tpl"
    assert destination.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")

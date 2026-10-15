"""Standard-library regressions plus direct execution of six existing test functions.

This is not pytest collection and does not replace the external pytest gate.
"""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.agent_system.setup_lifecycle_v32 import observe
from app.agent_system.setup_tracker_v31 import track_ict_setup


def load(name):
    path=Path(__file__).with_name(name+".py")
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy=load("test_agent_setup_lifecycle_v32")
tracker_tests=load("test_agent_setup_tracker_v31")


class V32RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=str(Path(self.temp.name)/"test.db")

    def test_nested_tracker_evidence_is_not_mutated(self):
        source=legacy.tracker()
        source["fvg"]=[99.,100.]
        saved=deepcopy(source)
        with patch("app.agent_system.setup_lifecycle_v32.track_ict_setup",return_value=source), patch("app.agent_system.setup_lifecycle_v32.scan_pois",return_value=[legacy.zone()]):
            observed=observe(legacy.snapshot(),"M1",self.path)
            observed["fvg"].append(999.)
            observed["blocks"].append("caller_change")
        self.assertEqual(source,saved)

    def test_poi_disappearance_is_terminal_across_restart(self):
        with patch("app.agent_system.setup_lifecycle_v32.track_ict_setup",side_effect=lambda *args:legacy.tracker()):
            with patch("app.agent_system.setup_lifecycle_v32.scan_pois",return_value=[legacy.zone()]):
                observe(legacy.snapshot(),"M1",self.path)
            with patch("app.agent_system.setup_lifecycle_v32.scan_pois",return_value=[]):
                lost=observe(legacy.snapshot(),"M1",self.path)
            with patch("app.agent_system.setup_lifecycle_v32.scan_pois",return_value=[legacy.zone()]):
                returned=observe(legacy.snapshot(),"M1",self.path)
        self.assertEqual(lost["status"],"INVALIDATED")
        self.assertEqual(returned["status"],"INVALIDATED")
        self.assertFalse(returned["confirmed_for_signal"])

    def test_tracker_rejects_unclosed_penultimate_bar(self):
        snap=tracker_tests.make_snapshot()
        as_of=datetime.fromtimestamp(snap.timeframes["M1"][-2]["time"]+30,timezone.utc)
        result=track_ict_setup(snap.model_copy(update={"as_of":as_of}),"M1")
        self.assertIn("candle_close_or_geometry_unverified",result["blocks"])

    def test_tracker_rejects_missing_or_duplicate_candle_identity(self):
        for missing in (True,False):
            snap=tracker_tests.make_snapshot(with_times=not missing)
            if not missing:
                rows=list(snap.timeframes["M1"])
                rows[1]=dict(rows[0])
                snap=snap.model_copy(update={"timeframes":{**snap.timeframes,"M1":tuple(rows)}})
            result=track_ict_setup(snap,"M1")
            self.assertIn("candle_close_or_geometry_unverified",result["blocks"])


def _wrap(function, temporary):
    def run(self):
        if temporary:
            with tempfile.TemporaryDirectory() as path:
                function(Path(path))
        else:
            function()
    return run


class ExistingV31V32Functions(unittest.TestCase):
    """Run existing assertions verbatim, adapting only pytest's tmp_path argument."""


for module,temporary in ((legacy,True),(tracker_tests,False)):
    for name in sorted(vars(module)):
        function=getattr(module,name)
        if name.startswith("test_") and callable(function):
            setattr(ExistingV31V32Functions,"test_"+module.__name__+"_"+name,_wrap(function,temporary))


if __name__=="__main__":
    unittest.main()

import ast
import unittest
from pathlib import Path

class ResultFlowStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path(__file__).resolve().parents[1] / 'app' / 'main.py'
        cls.source = cls.path.read_text(encoding='utf-8')
        cls.tree = ast.parse(cls.source)

    def _function(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
        self.fail(f'{name} not found')

    def test_result_publisher_sends_text_only(self):
        fn = self._function('_publish_result_to_channel')
        send_photo = []
        send_message = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == 'send_photo': send_photo.append(node)
                if node.func.attr == 'send_message': send_message.append(node)
        self.assertEqual(len(send_photo), 0)
        self.assertEqual(len(send_message), 1)

    def test_result_fallback_has_no_chart_argument(self):
        fn = self._function('_publish_result_with_fallback')
        args = list(fn.args.args)
        self.assertEqual([a.arg for a in args], ['bot','target','row','last_message_id','original_message_id','caption','label'])

    def test_mt5_close_handler_is_text_only(self):
        fn = self._function('_process_mt5_trade_event')
        segment = ast.get_source_segment(self.source, fn) or ''
        close_pos = segment.find('if event == "CLOSE":')
        self.assertGreaterEqual(close_pos, 0)
        close_segment = segment[close_pos:]
        self.assertNotIn('build_chart_frame', close_segment)
        self.assertNotIn('send_photo', close_segment)

    def test_manual_close_flow_does_not_request_photo(self):
        fn = self._function('signal_close_exit_input')
        segment = ast.get_source_segment(self.source, fn) or ''
        self.assertNotIn('Flow.signal_close_chart', segment)
        self.assertNotIn('final result chart', segment)

if __name__ == '__main__':
    unittest.main()

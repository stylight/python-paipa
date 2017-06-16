"""
Developer didn't bother writing documentation.
"""
import unittest

import mock

from paipa import debugger, debug_reporter, combine_pipeline, consume


class TestPipelineDebugger(unittest.TestCase):

    def test_pipeline_debugger(self):
        logger = mock.Mock()
        mock_reporter = mock.Mock()
        dbg = debugger.PipelineRuntimeDebugger(
            reporters=[debug_reporter.LoggingReporter(logger),
                       mock_reporter])

        pipeline = combine_pipeline(
            range(10),
            [lambda x: x],
            debugger=dbg
        )
        consume(pipeline)
        assert logger.info.call_count == 2
        assert mock_reporter.show.call_count == 1


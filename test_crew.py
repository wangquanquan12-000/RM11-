import unittest
from unittest.mock import patch, MagicMock, call
import sys

# To test a script, we need to make sure we can import it.
# We also need a way to reload it for different test conditions.
# If crew_test was already imported, remove it to ensure a clean import.
if 'crew_test' in sys.modules:
    del sys.modules['crew_test']

import importlib

class TestCrewScript(unittest.TestCase):

    def setUp(self):
        """
        This method is called before each test. It ensures that 'crew_test'
        is removed from modules, so it can be freshly imported in each test.
        """
        if 'crew_test' in sys.modules:
            del sys.modules['crew_test']

    @patch('os.getenv')
    @patch('langchain_google_genai.ChatGoogleGenerativeAI')
    @patch('crewai.Agent')
    @patch('crewai.Task')
    @patch('crewai.Crew')
    def test_script_initialization_flow(self, MockCrew, MockTask, MockAgent, MockChatGoogleGenerativeAI, mock_getenv):
        """
        Tests the main flow of the script upon import:
        - API key is checked.
        - LLM is initialized.
        - Agents, Tasks, and a Crew are created with the correct parameters.
        """
        # --- Arrange ---
        # Mock the environment variable and the crew kickoff to prevent execution
        mock_api_key = "test_api_key"
        mock_getenv.return_value = mock_api_key
        mock_crew_instance = MagicMock()
        MockCrew.return_value = mock_crew_instance
        mock_llm_instance = MagicMock()
        MockChatGoogleGenerativeAI.return_value = mock_llm_instance

        # --- Act ---
        # Importing the script runs its top-level code
        import crew_test

        # --- Assert ---
        # 1. API Key check
        mock_getenv.assert_called_once_with("GEMINI_API_KEY")

        # 2. LLM Initialization
        MockChatGoogleGenerativeAI.assert_called_once_with(
            model="gemini-1.5-pro",
            google_api_key=mock_api_key
        )

        # 3. Agent Creation
        self.assertEqual(MockAgent.call_count, 4, "Should create 4 agents")
        agent_calls = [
            call(role='Document Analyst', goal='Find issues in requirement documents.', backstory='You are a senior requirements analyst.', llm=mock_llm_instance, verbose=True),
            call(role='Requirements Analyst', goal='Organize requirements based on analysis.', backstory='You are a professional requirements organizer.', llm=mock_llm_instance, verbose=True),
            call(role='Test Case Engineer', goal='Generate complete test cases.', backstory='You are a senior test case writer.', llm=mock_llm_instance, verbose=True),
            call(role='QA Reviewer', goal='Review test cases for coverage and correctness.', backstory='You are a strict QA reviewer.', llm=mock_llm_instance, verbose=True)
        ]
        MockAgent.assert_has_calls(agent_calls, any_order=True)

        # 4. Task Creation
        self.assertEqual(MockTask.call_count, 4, "Should create 4 tasks")

        # 5. Crew Creation
        MockCrew.assert_called_once()
        args, kwargs = MockCrew.call_args
        self.assertEqual(len(kwargs['agents']), 4, "Crew should have 4 agents")
        self.assertEqual(len(kwargs['tasks']), 4, "Crew should have 4 tasks")
        self.assertEqual(kwargs['verbose'], 2, "Crew verbose level should be 2")

        # 6. Kickoff is NOT called on import, because it's in the __main__ block
        mock_crew_instance.kickoff.assert_not_called()

    @patch('os.getenv')
    def test_api_key_not_set_raises_error(self, mock_getenv):
        """
        Tests that a ValueError is raised if the API key environment variable is not set.
        """
        # --- Arrange ---
        # Simulate the environment variable not being set
        mock_getenv.return_value = None

        # --- Act & Assert ---
        # Check that importing the script raises the specific ValueError
        with self.assertRaisesRegex(ValueError, "ERROR: GEMINI_API_KEY environment variable is not set."):
            importlib.import_module('crew_test')


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

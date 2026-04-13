"""Unit tests for Jira utility scripts."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add scripts/jira to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "jira"))

from client import JiraClient
from get_issue import get_issue, main as get_issue_main
from search_issues import search_issues, main as search_issues_main, keyword_to_jql, epic_to_jql
from create_issue import create_issue, main as create_issue_main, ACTIVITY_TYPES
from update_issue import update_issue, main as update_issue_main
from link_issues import link_issues, main as link_issues_main
from get_sprint import get_sprint, main as get_sprint_main
from get_board import get_boards, main as get_board_main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None, content=b"{}"):
    resp = Mock()
    resp.status_code = status_code
    resp.content = content
    resp.url = "https://jira.example.com/rest/api/2/issue/PROJ-1"
    resp.text = json.dumps(json_data) if json_data else ""
    resp.json.return_value = json_data or {}
    return resp


def _make_client(monkeypatch=None):
    """Return a JiraClient with env vars set and session mocked."""
    with patch.dict("os.environ", {
        "JIRA_BASE_URL": "https://jira.example.com",
        "JIRA_TOKEN": "test-token",
        "JIRA_EMAIL": "user@example.com",
        "JIRA_AUTH_TYPE": "cloud",
    }):
        return JiraClient()


# ---------------------------------------------------------------------------
# JiraClient
# ---------------------------------------------------------------------------

class TestJiraClient:
    """Tests for the shared JiraClient."""

    def test_cloud_auth_sets_basic_auth(self):
        with patch.dict("os.environ", {
            "JIRA_BASE_URL": "https://jira.example.com",
            "JIRA_TOKEN": "token123",
            "JIRA_EMAIL": "user@example.com",
            "JIRA_AUTH_TYPE": "cloud",
        }):
            client = JiraClient()
            assert client.session.auth == ("user@example.com", "token123")
            assert "Authorization" not in client.session.headers

    def test_datacenter_auth_sets_bearer(self):
        with patch.dict("os.environ", {
            "JIRA_BASE_URL": "https://jira.example.com",
            "JIRA_TOKEN": "my-pat",
            "JIRA_AUTH_TYPE": "datacenter",
        }):
            client = JiraClient()
            assert client.session.headers["Authorization"] == "Bearer my-pat"
            assert client.session.auth is None

    @pytest.mark.parametrize("missing_env, match", [
        ({"JIRA_TOKEN": ""}, "JIRA_TOKEN"),
        ({"JIRA_BASE_URL": ""}, "JIRA_BASE_URL"),
        ({"JIRA_EMAIL": ""}, "JIRA_EMAIL"),
    ])
    def test_missing_credentials_raises(self, missing_env, match):
        env = {
            "JIRA_BASE_URL": "https://jira.example.com",
            "JIRA_TOKEN": "token123",
            "JIRA_EMAIL": "user@example.com",
            "JIRA_AUTH_TYPE": "cloud",
        }
        env.update(missing_env)
        with patch.dict("os.environ", env, clear=False):
            # Temporarily remove the key if set to empty
            for k, v in missing_env.items():
                if not v:
                    env.pop(k, None)
            with patch.dict("os.environ", env, clear=True):
                with pytest.raises(ValueError, match=match):
                    JiraClient()

    def test_trailing_slash_stripped_from_base_url(self):
        with patch.dict("os.environ", {
            "JIRA_BASE_URL": "https://jira.example.com/",
            "JIRA_TOKEN": "token",
            "JIRA_EMAIL": "user@example.com",
        }):
            client = JiraClient()
            assert client.base_url == "https://jira.example.com"

    def test_raises_value_error_on_401(self):
        with patch.dict("os.environ", {
            "JIRA_BASE_URL": "https://jira.example.com",
            "JIRA_TOKEN": "bad-token",
            "JIRA_EMAIL": "user@example.com",
        }):
            client = JiraClient()
            resp = _mock_response(status_code=401)
            with pytest.raises(ValueError, match="Authentication failed"):
                client._raise_for_status(resp)

    def test_raises_lookup_error_on_404(self):
        with patch.dict("os.environ", {
            "JIRA_BASE_URL": "https://jira.example.com",
            "JIRA_TOKEN": "token",
            "JIRA_EMAIL": "user@example.com",
        }):
            client = JiraClient()
            resp = _mock_response(status_code=404)
            with pytest.raises(LookupError, match="not found"):
                client._raise_for_status(resp)

    def test_raises_runtime_error_on_500(self):
        with patch.dict("os.environ", {
            "JIRA_BASE_URL": "https://jira.example.com",
            "JIRA_TOKEN": "token",
            "JIRA_EMAIL": "user@example.com",
        }):
            client = JiraClient()
            resp = _mock_response(
                status_code=500,
                json_data={"errorMessages": ["Internal Server Error"]}
            )
            resp.json.return_value = {"errorMessages": ["Internal Server Error"]}
            with pytest.raises(RuntimeError, match="Jira API error"):
                client._raise_for_status(resp)

    def test_get_returns_204_as_empty_dict(self):
        with patch.dict("os.environ", {
            "JIRA_BASE_URL": "https://jira.example.com",
            "JIRA_TOKEN": "token",
            "JIRA_EMAIL": "user@example.com",
        }):
            client = JiraClient()
            resp = _mock_response(status_code=204, content=b"")
            with patch.object(client.session, "put", return_value=resp):
                result = client.put("/rest/api/2/issue/PROJ-1", json={})
                assert result == {}


# ---------------------------------------------------------------------------
# get_issue
# ---------------------------------------------------------------------------

class TestGetIssue:
    """Tests for get_issue function."""

    @patch("get_issue.JiraClient")
    def test_get_issue_success(self, MockClient):
        issue_data = {"id": "10001", "key": "PROJ-1", "fields": {"summary": "Fix bug"}}
        MockClient.return_value.get.return_value = issue_data

        result = get_issue("PROJ-1", base_url="https://jira.example.com",
                           token="tok", email="u@e.com")
        assert result["key"] == "PROJ-1"
        MockClient.return_value.get.assert_called_once_with("/rest/api/3/issue/PROJ-1")

    @patch("get_issue.JiraClient")
    def test_get_issue_not_found(self, MockClient):
        MockClient.return_value.get.side_effect = LookupError("not found")
        with pytest.raises(LookupError):
            get_issue("PROJ-999", base_url="https://jira.example.com",
                      token="tok", email="u@e.com")

    @pytest.mark.parametrize("side_effect, exit_code", [
        (LookupError("not found"), 3),
        (RuntimeError("API error"), 2),
        (ValueError("Authentication failed"), 4),
    ])
    @patch("get_issue.JiraClient")
    @patch("sys.argv", ["get_issue.py", "PROJ-1"])
    def test_main_errors(self, MockClient, side_effect, exit_code):
        MockClient.return_value.get.side_effect = side_effect
        assert get_issue_main() == exit_code

    @patch("get_issue.JiraClient")
    @patch("sys.argv", ["get_issue.py", "PROJ-1"])
    def test_main_success(self, MockClient):
        MockClient.return_value.get.return_value = {"key": "PROJ-1"}
        assert get_issue_main() == 0


# ---------------------------------------------------------------------------
# search_issues
# ---------------------------------------------------------------------------

class TestSearchIssues:
    """Tests for search_issues function."""

    @patch("search_issues.JiraClient")
    def test_search_returns_issues(self, MockClient):
        MockClient.return_value.post.return_value = {
            "issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}],
            "total": 2,
        }
        result = search_issues('project = PROJ', base_url="https://j.com",
                               token="tok", email="u@e.com")
        assert len(result) == 2
        assert result[0]["key"] == "PROJ-1"

    def test_empty_jql_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            search_issues("", base_url="https://j.com", token="tok", email="u@e.com")

    @patch("search_issues.JiraClient")
    def test_search_passes_params(self, MockClient):
        MockClient.return_value.post.return_value = {"issues": [], "total": 0}
        search_issues('project = PROJ', max_results=10, fields="summary,status",
                      base_url="https://j.com", token="tok", email="u@e.com")
        body = MockClient.return_value.post.call_args.kwargs["json"]
        assert body["maxResults"] == 10
        assert body["fields"] == ["summary", "status"]

    @pytest.mark.parametrize("side_effect, exit_code", [
        (RuntimeError("API error"), 2),
        (ValueError("Authentication failed"), 4),
        (LookupError("not found"), 3),
    ])
    @patch("search_issues.JiraClient")
    @patch("sys.argv", ["search_issues.py", "project = PROJ"])
    def test_main_errors(self, MockClient, side_effect, exit_code):
        MockClient.return_value.post.side_effect = side_effect
        assert search_issues_main() == exit_code

    @patch("search_issues.JiraClient")
    @patch("sys.argv", ["search_issues.py", "project = PROJ"])
    def test_main_success(self, MockClient):
        MockClient.return_value.post.return_value = {"issues": [], "total": 0}
        assert search_issues_main() == 0

    def test_keyword_to_jql_basic(self):
        assert keyword_to_jql("alice") == 'text ~ "alice"'

    def test_keyword_to_jql_with_project(self):
        assert keyword_to_jql("alice", project="MYPROJ") == 'project = MYPROJ AND text ~ "alice"'

    def test_keyword_to_jql_escapes_quotes(self):
        assert keyword_to_jql('say "hello"') == 'text ~ "say \\"hello\\""'

    def test_epic_to_jql(self):
        assert epic_to_jql("PROJ-42") == '"Epic Link" = PROJ-42 OR parent = PROJ-42'

    @patch("search_issues.JiraClient")
    @patch("sys.argv", ["search_issues.py", "--search", "alice"])
    def test_main_search_flag(self, MockClient):
        MockClient.return_value.post.return_value = {"issues": [], "total": 0}
        assert search_issues_main() == 0
        body = MockClient.return_value.post.call_args.kwargs["json"]
        assert body["jql"] == 'text ~ "alice"'

    @patch("search_issues.JiraClient")
    @patch("sys.argv", ["search_issues.py", "--search", "alice", "--project", "MYPROJ"])
    def test_main_search_flag_with_project(self, MockClient):
        MockClient.return_value.post.return_value = {"issues": [], "total": 0}
        assert search_issues_main() == 0
        body = MockClient.return_value.post.call_args.kwargs["json"]
        assert body["jql"] == 'project = MYPROJ AND text ~ "alice"'

    @patch("search_issues.JiraClient")
    @patch("sys.argv", ["search_issues.py", "--epic", "PROJ-42"])
    def test_main_epic_flag(self, MockClient):
        MockClient.return_value.post.return_value = {"issues": [], "total": 0}
        assert search_issues_main() == 0
        body = MockClient.return_value.post.call_args.kwargs["json"]
        assert body["jql"] == '"Epic Link" = PROJ-42 OR parent = PROJ-42'

    @patch("sys.argv", ["search_issues.py", "--search", "alice", "project = PROJ"])
    def test_main_search_and_jql_is_error(self):
        assert search_issues_main() == 1

    @patch("sys.argv", ["search_issues.py", "--search", "foo", "--epic", "PROJ-42"])
    def test_main_search_and_epic_is_error(self):
        assert search_issues_main() == 1

    @patch("sys.argv", ["search_issues.py"])
    def test_main_no_jql_no_search_is_error(self):
        assert search_issues_main() == 1

    @patch("search_issues.JiraClient")
    @patch("sys.argv", ["search_issues.py", "project = PROJ", "--format", "table"])
    def test_main_format_table(self, MockClient, capsys):
        MockClient.return_value.post.return_value = {
            "issues": [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "issuetype": {"name": "Task"},
                        "status": {"name": "In Progress"},
                        "assignee": {"displayName": "Alice"},
                        "summary": "Do something",
                    },
                }
            ],
            "total": 1,
        }
        rc = search_issues_main()
        assert rc == 0
        captured = capsys.readouterr()
        assert "PROJ-1" in captured.out
        assert "Task" in captured.out
        assert "In Progress" in captured.out
        assert "Alice" in captured.out
        assert "Do something" in captured.out
        # Must NOT be JSON
        with pytest.raises(Exception):
            json.loads(captured.out)


# ---------------------------------------------------------------------------
# create_issue
# ---------------------------------------------------------------------------

class TestCreateIssue:
    """Tests for create_issue function."""

    @patch("create_issue.JiraClient")
    def test_create_issue_success(self, MockClient):
        MockClient.return_value.post.return_value = {
            "id": "10001", "key": "PROJ-5", "self": "https://..."
        }
        result = create_issue("PROJ", "New feature", description="Details",
                              base_url="https://j.com", token="tok", email="u@e.com")
        assert result["key"] == "PROJ-5"

    @patch("create_issue.JiraClient")
    def test_create_issue_sends_correct_fields(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        create_issue("PROJ", "Summary", description="Desc", issuetype="Bug",
                     priority="High", labels=["backend", "urgent"],
                     base_url="https://j.com", token="tok", email="u@e.com")
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        fields = payload["fields"]
        assert fields["project"] == {"key": "PROJ"}
        assert fields["summary"] == "Summary"
        assert fields["issuetype"] == {"name": "Bug"}
        assert fields["priority"] == {"name": "High"}
        assert fields["labels"] == ["backend", "urgent"]

    @patch("create_issue.JiraClient")
    def test_create_issue_description_wrapped_in_adf(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        create_issue("PROJ", "Summary", description="Plain text description",
                     base_url="https://j.com", token="tok", email="u@e.com")
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        desc = payload["fields"]["description"]
        assert desc["version"] == 1
        assert desc["type"] == "doc"
        assert desc["content"][0]["type"] == "paragraph"
        assert desc["content"][0]["content"][0] == {"type": "text", "text": "Plain text description"}

    @pytest.mark.parametrize("project, summary, match", [
        ("", "Summary", "Project key"),
        ("PROJ", "", "Summary"),
    ])
    def test_missing_required_fields_raises(self, project, summary, match):
        with pytest.raises(ValueError, match=match):
            create_issue(project, summary, base_url="https://j.com",
                         token="tok", email="u@e.com")

    @pytest.mark.parametrize("side_effect, exit_code", [
        (RuntimeError("API error"), 2),
        (ValueError("Authentication failed"), 4),
        (LookupError("not found"), 3),
    ])
    @patch("create_issue.JiraClient")
    @patch("sys.argv", ["create_issue.py", "PROJ", "My issue"])
    def test_main_errors(self, MockClient, side_effect, exit_code):
        MockClient.return_value.post.side_effect = side_effect
        assert create_issue_main() == exit_code

    @patch("create_issue.JiraClient")
    @patch("sys.argv", ["create_issue.py", "PROJ", "My issue",
                         "--labels", "backend,urgent", "--priority", "High"])
    def test_main_with_labels(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        assert create_issue_main() == 0
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["labels"] == ["backend", "urgent"]

    @patch("create_issue.JiraClient")
    def test_create_issue_with_team(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        team_id = "12345678-1234-5678-9abc-def012345678"
        create_issue("PROJ", "Summary", team=team_id,
                     base_url="https://j.com", token="tok", email="u@e.com")
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        # Team field must be a plain string ID, not wrapped in an object
        assert payload["fields"]["customfield_10001"] == team_id

    @patch("create_issue.JiraClient")
    @patch("sys.argv", ["create_issue.py", "PROJ", "My issue",
                        "--team", "12345678-1234-5678-9abc-def012345678"])
    def test_main_with_team(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        assert create_issue_main() == 0
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["customfield_10001"] == "12345678-1234-5678-9abc-def012345678"

    @patch("create_issue.JiraClient")
    def test_create_issue_assignee_uses_account_id_for_cloud(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        create_issue("PROJ", "Summary", assignee="712020:abc-123",
                     base_url="https://j.com", token="tok", email="u@e.com", auth_type="cloud")
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["assignee"] == {"accountId": "712020:abc-123"}

    @patch("create_issue.JiraClient")
    def test_create_issue_assignee_uses_name_for_datacenter(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        create_issue("PROJ", "Summary", assignee="jdoe",
                     base_url="https://j.com", token="tok", auth_type="datacenter")
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["assignee"] == {"name": "jdoe"}

    @patch("create_issue.JiraClient")
    def test_create_issue_with_epic_uses_parent_field(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        create_issue("PROJ", "Summary", epic="PROJ-42",
                     base_url="https://j.com", token="tok", email="u@e.com")
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["parent"] == {"key": "PROJ-42"}
        assert "customfield_10014" not in payload["fields"]

    @patch("create_issue.JiraClient")
    def test_create_issue_with_epic_falls_back_to_customfield(self, MockClient):
        # First call (parent field) raises a field error; second call succeeds.
        MockClient.return_value.post.side_effect = [
            RuntimeError("Field 'parent' cannot be set"),
            {"key": "PROJ-5"},
        ]
        result = create_issue("PROJ", "Summary", epic="PROJ-42",
                              base_url="https://j.com", token="tok", email="u@e.com")
        assert result["key"] == "PROJ-5"
        assert MockClient.return_value.post.call_count == 2
        # Second call must use the classic Epic Link field
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["customfield_10014"] == "PROJ-42"
        assert "parent" not in payload["fields"]

    @patch("create_issue.JiraClient")
    def test_create_issue_epic_non_field_error_is_reraised(self, MockClient):
        # A non-field-related error should not trigger the fallback.
        MockClient.return_value.post.side_effect = RuntimeError("Network timeout")
        with pytest.raises(RuntimeError, match="Network timeout"):
            create_issue("PROJ", "Summary", epic="PROJ-42",
                         base_url="https://j.com", token="tok", email="u@e.com")
        assert MockClient.return_value.post.call_count == 1

    @patch("create_issue.JiraClient")
    @patch("sys.argv", ["create_issue.py", "PROJ", "My issue", "--epic", "PROJ-42"])
    def test_main_with_epic(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        assert create_issue_main() == 0
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["parent"] == {"key": "PROJ-42"}

    @pytest.mark.parametrize("activity_type", ACTIVITY_TYPES)
    @patch("create_issue.JiraClient")
    def test_create_issue_with_activity_type(self, MockClient, activity_type):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        create_issue("PROJ", "Summary", activity_type=activity_type,
                     base_url="https://j.com", token="tok", email="u@e.com")
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["customfield_10464"] == {"value": activity_type}

    def test_invalid_activity_type_raises(self):
        with pytest.raises(ValueError, match="Invalid activity_type"):
            create_issue("PROJ", "Summary", activity_type="Invalid Value",
                         base_url="https://j.com", token="tok", email="u@e.com")

    @patch("create_issue.JiraClient")
    @patch("sys.argv", ["create_issue.py", "PROJ", "My issue",
                        "--activity-type", "New Features"])
    def test_main_with_activity_type(self, MockClient):
        MockClient.return_value.post.return_value = {"key": "PROJ-5"}
        assert create_issue_main() == 0
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["fields"]["customfield_10464"] == {"value": "New Features"}


# ---------------------------------------------------------------------------
# update_issue
# ---------------------------------------------------------------------------

class TestUpdateIssue:
    """Tests for update_issue function."""

    @patch("update_issue.JiraClient")
    def test_update_issue_success(self, MockClient):
        MockClient.return_value.put.return_value = {}
        result = update_issue("PROJ-1", priority="High",
                              base_url="https://j.com", token="tok", email="u@e.com")
        assert result == {}

    @patch("update_issue.JiraClient")
    def test_update_sends_only_provided_fields(self, MockClient):
        MockClient.return_value.put.return_value = {}
        update_issue("PROJ-1", summary="New title",
                     base_url="https://j.com", token="tok", email="u@e.com")
        payload = MockClient.return_value.put.call_args.kwargs["json"]
        assert "summary" in payload["fields"]
        assert "priority" not in payload["fields"]
        assert "description" not in payload["fields"]

    def test_no_fields_raises(self):
        with pytest.raises(ValueError, match="No fields"):
            update_issue("PROJ-1", base_url="https://j.com",
                         token="tok", email="u@e.com")

    @pytest.mark.parametrize("side_effect, exit_code", [
        (LookupError("not found"), 3),
        (RuntimeError("API error"), 2),
        (ValueError("Authentication failed"), 4),
    ])
    @patch("update_issue.JiraClient")
    @patch("sys.argv", ["update_issue.py", "PROJ-1", "--priority", "High"])
    def test_main_errors(self, MockClient, side_effect, exit_code):
        MockClient.return_value.put.side_effect = side_effect
        assert update_issue_main() == exit_code

    @patch("update_issue.JiraClient")
    @patch("sys.argv", ["update_issue.py", "PROJ-1", "--priority", "Critical",
                         "--labels", "blocker,urgent"])
    def test_main_with_labels(self, MockClient):
        MockClient.return_value.put.return_value = {}
        assert update_issue_main() == 0
        payload = MockClient.return_value.put.call_args.kwargs["json"]
        assert payload["fields"]["labels"] == ["blocker", "urgent"]


# ---------------------------------------------------------------------------
# link_issues
# ---------------------------------------------------------------------------

class TestLinkIssues:
    """Tests for link_issues function."""

    @patch("link_issues.JiraClient")
    def test_link_issues_success(self, MockClient):
        MockClient.return_value.post.return_value = {}
        result = link_issues("PROJ-1", "PROJ-2", link_type="blocks",
                             base_url="https://j.com", token="tok", email="u@e.com")
        assert result == {}

    @patch("link_issues.JiraClient")
    def test_link_sends_correct_payload(self, MockClient):
        MockClient.return_value.post.return_value = {}
        link_issues("PROJ-1", "PROJ-2", link_type="duplicates",
                    base_url="https://j.com", token="tok", email="u@e.com")
        payload = MockClient.return_value.post.call_args.kwargs["json"]
        assert payload["type"] == {"name": "duplicates"}
        assert payload["inwardIssue"] == {"key": "PROJ-1"}
        assert payload["outwardIssue"] == {"key": "PROJ-2"}

    @pytest.mark.parametrize("inward, outward, match", [
        ("", "PROJ-2", "inward_key"),
        ("PROJ-1", "", "outward_key"),
    ])
    def test_missing_keys_raises(self, inward, outward, match):
        with pytest.raises(ValueError, match=match):
            link_issues(inward, outward,
                        base_url="https://j.com", token="tok", email="u@e.com")

    @pytest.mark.parametrize("side_effect, exit_code", [
        (LookupError("not found"), 3),
        (RuntimeError("API error"), 2),
        (ValueError("Authentication failed"), 4),
    ])
    @patch("link_issues.JiraClient")
    @patch("sys.argv", ["link_issues.py", "PROJ-1", "PROJ-2"])
    def test_main_errors(self, MockClient, side_effect, exit_code):
        MockClient.return_value.post.side_effect = side_effect
        assert link_issues_main() == exit_code

    @patch("link_issues.JiraClient")
    @patch("sys.argv", ["link_issues.py", "PROJ-1", "PROJ-2", "--link-type", "blocks"])
    def test_main_success(self, MockClient):
        MockClient.return_value.post.return_value = {}
        assert link_issues_main() == 0


# ---------------------------------------------------------------------------
# get_sprint
# ---------------------------------------------------------------------------

class TestGetSprint:
    """Tests for get_sprint function."""

    @patch("get_sprint.JiraClient")
    def test_get_active_sprint(self, MockClient):
        sprint_data = [{"id": 1, "name": "Sprint 42", "state": "active"}]
        MockClient.return_value.get.return_value = {"values": sprint_data}

        result = get_sprint(board_id=10, state="active",
                            base_url="https://j.com", token="tok", email="u@e.com")
        assert len(result) == 1
        assert result[0]["name"] == "Sprint 42"

    @patch("get_sprint.JiraClient")
    def test_get_sprint_passes_state_param(self, MockClient):
        MockClient.return_value.get.return_value = {"values": []}
        get_sprint(board_id=10, state="future",
                   base_url="https://j.com", token="tok", email="u@e.com")
        call_params = MockClient.return_value.get.call_args.kwargs["params"]
        assert call_params["state"] == "future"

    def test_invalid_state_raises(self):
        with pytest.raises(ValueError, match="Invalid state"):
            get_sprint(board_id=10, state="invalid",
                       base_url="https://j.com", token="tok", email="u@e.com")

    @pytest.mark.parametrize("side_effect, exit_code", [
        (LookupError("board not found"), 3),
        (RuntimeError("API error"), 2),
        (ValueError("Authentication failed"), 4),
    ])
    @patch("get_sprint.JiraClient")
    @patch("sys.argv", ["get_sprint.py", "10"])
    def test_main_errors(self, MockClient, side_effect, exit_code):
        MockClient.return_value.get.side_effect = side_effect
        assert get_sprint_main() == exit_code

    @patch("get_sprint.JiraClient")
    @patch("sys.argv", ["get_sprint.py", "10", "--state", "future"])
    def test_main_success(self, MockClient):
        MockClient.return_value.get.return_value = {"values": [{"id": 2}]}
        assert get_sprint_main() == 0

    @patch("sys.argv", ["get_sprint.py"])
    def test_main_no_board_id_no_project_returns_1(self):
        assert get_sprint_main() == 1

    @patch("get_sprint.get_boards")
    @patch("get_sprint.JiraClient")
    @patch("sys.argv", ["get_sprint.py", "--project", "MYPROJ"])
    def test_main_project_discovers_single_board(self, MockClient, mock_get_boards):
        mock_get_boards.return_value = [
            {"id": 42, "name": "My Team Board", "type": "scrum"}
        ]
        MockClient.return_value.get.return_value = {
            "values": [{"id": 1, "name": "Sprint 1", "state": "active"}]
        }
        assert get_sprint_main() == 0
        call_path = MockClient.return_value.get.call_args[0][0]
        assert "42" in call_path

    @patch("get_sprint.get_boards")
    @patch("sys.argv", ["get_sprint.py", "--project", "MYPROJ"])
    def test_main_project_no_boards_returns_3(self, mock_get_boards):
        mock_get_boards.return_value = []
        assert get_sprint_main() == 3

    @patch("get_sprint.get_boards")
    @patch("sys.argv", ["get_sprint.py", "--project", "MYPROJ"])
    def test_main_project_multiple_boards_returns_1(self, mock_get_boards):
        mock_get_boards.return_value = [
            {"id": 1, "name": "Board A", "type": "scrum"},
            {"id": 2, "name": "Board B", "type": "scrum"},
        ]
        assert get_sprint_main() == 1

    @patch("get_sprint.get_boards")
    @patch("get_sprint.JiraClient")
    @patch("sys.argv", ["get_sprint.py", "--project", "MYPROJ", "--board-name", "My Team", "--board-type", "scrum"])
    def test_main_project_with_board_name_and_type(self, MockClient, mock_get_boards):
        mock_get_boards.return_value = [
            {"id": 42, "name": "My Team Board", "type": "scrum"}
        ]
        MockClient.return_value.get.return_value = {"values": []}
        assert get_sprint_main() == 0
        mock_get_boards.assert_called_once_with(
            project="MYPROJ", name_filter="My Team", board_type="scrum"
        )


# ---------------------------------------------------------------------------
# get_board
# ---------------------------------------------------------------------------

class TestGetBoard:
    """Tests for get_boards function and get_board main."""

    @patch("get_board.JiraClient")
    def test_get_boards_returns_all(self, MockClient):
        board_data = [
            {"id": 1, "name": "Board A", "type": "scrum"},
            {"id": 2, "name": "Board B", "type": "kanban"},
        ]
        MockClient.return_value.get.return_value = {"values": board_data, "isLast": True}
        result = get_boards("PROJ", base_url="https://j.com", token="tok", email="u@e.com")
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Board A"
        assert result[0]["type"] == "scrum"

    @patch("get_board.JiraClient")
    def test_get_boards_name_filter_case_insensitive(self, MockClient):
        board_data = [
            {"id": 1, "name": "My Team Board", "type": "scrum"},
            {"id": 2, "name": "My Other Board", "type": "scrum"},
        ]
        MockClient.return_value.get.return_value = {"values": board_data, "isLast": True}
        result = get_boards("MYPROJ", name_filter="TEAM",
                            base_url="https://j.com", token="tok", email="u@e.com")
        assert len(result) == 1
        assert result[0]["id"] == 1

    @patch("get_board.JiraClient")
    def test_get_boards_type_filter(self, MockClient):
        board_data = [
            {"id": 1, "name": "Scrum Board", "type": "scrum"},
            {"id": 2, "name": "Kanban Board", "type": "kanban"},
        ]
        MockClient.return_value.get.return_value = {"values": board_data, "isLast": True}
        result = get_boards("PROJ", board_type="kanban",
                            base_url="https://j.com", token="tok", email="u@e.com")
        assert len(result) == 1
        assert result[0]["type"] == "kanban"

    @patch("get_board.JiraClient")
    def test_get_boards_paginates(self, MockClient):
        page1 = {
            "values": [{"id": i, "name": f"Board {i}", "type": "scrum"} for i in range(50)],
            "isLast": False,
        }
        page2 = {
            "values": [{"id": i, "name": f"Board {i}", "type": "scrum"} for i in range(50, 60)],
            "isLast": True,
        }
        MockClient.return_value.get.side_effect = [page1, page2]
        result = get_boards("PROJ", base_url="https://j.com", token="tok", email="u@e.com")
        assert len(result) == 60
        assert MockClient.return_value.get.call_count == 2

    @patch("get_board.JiraClient")
    def test_get_boards_passes_project_param(self, MockClient):
        MockClient.return_value.get.return_value = {"values": [], "isLast": True}
        get_boards("MYPROJ", base_url="https://j.com", token="tok", email="u@e.com")
        params = MockClient.return_value.get.call_args.kwargs["params"]
        assert params["projectKeyOrId"] == "MYPROJ"

    def test_empty_project_raises(self):
        with pytest.raises(ValueError, match="Project key"):
            get_boards("", base_url="https://j.com", token="tok", email="u@e.com")

    def test_invalid_board_type_raises(self):
        with pytest.raises(ValueError, match="Invalid board_type"):
            get_boards("PROJ", board_type="invalid",
                       base_url="https://j.com", token="tok", email="u@e.com")

    @patch("get_board.JiraClient")
    @patch("sys.argv", ["get_board.py", "MYPROJ"])
    def test_main_success(self, MockClient):
        MockClient.return_value.get.return_value = {
            "values": [{"id": 42, "name": "My Board", "type": "scrum"}],
            "isLast": True,
        }
        assert get_board_main() == 0

    @patch("get_board.JiraClient")
    @patch("sys.argv", ["get_board.py", "MYPROJ", "--first"])
    def test_main_first_flag_returns_single_object(self, MockClient, capsys):
        MockClient.return_value.get.return_value = {
            "values": [
                {"id": 1, "name": "Board A", "type": "scrum"},
                {"id": 2, "name": "Board B", "type": "scrum"},
            ],
            "isLast": True,
        }
        rc = get_board_main()
        assert rc == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert isinstance(output, dict)
        assert output["id"] == 1

    @patch("get_board.JiraClient")
    @patch("sys.argv", ["get_board.py", "MYPROJ"])
    def test_main_no_boards_returns_3(self, MockClient):
        MockClient.return_value.get.return_value = {"values": [], "isLast": True}
        assert get_board_main() == 3

    @patch("get_board.JiraClient")
    @patch("sys.argv", ["get_board.py", "MYPROJ", "--name", "My Team", "--type", "scrum"])
    def test_main_with_name_and_type_filters(self, MockClient, capsys):
        MockClient.return_value.get.return_value = {
            "values": [
                {"id": 42, "name": "My Team Board", "type": "scrum"},
                {"id": 100, "name": "My General Board", "type": "scrum"},
            ],
            "isLast": True,
        }
        rc = get_board_main()
        assert rc == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output) == 1
        assert output[0]["id"] == 42

    @pytest.mark.parametrize("side_effect, exit_code", [
        (RuntimeError("API error"), 2),
        (ValueError("Authentication failed"), 4),
        (LookupError("not found"), 3),
    ])
    @patch("get_board.JiraClient")
    @patch("sys.argv", ["get_board.py", "PROJ"])
    def test_main_errors(self, MockClient, side_effect, exit_code):
        MockClient.return_value.get.side_effect = side_effect
        assert get_board_main() == exit_code

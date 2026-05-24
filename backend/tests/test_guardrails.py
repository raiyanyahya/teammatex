"""Test the guardrail system for secrets, SQL injection, and dangerous calls."""

import pytest

from app.services.agent.guardrails import guardrails, GuardResult


class TestSecretDetection:
    def test_detect_aws_key(self):
        code = 'AWS_ACCESS_KEY = "AKIA1234567890ABCDEF"'
        result = guardrails.run_all_checks(code)
        assert result == GuardResult.BLOCK

    def test_detect_github_token(self):
        code = 'token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"'
        result = guardrails.run_all_checks(code)
        assert result == GuardResult.BLOCK

    def test_detect_private_key(self):
        code = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        result = guardrails.run_all_checks(code)
        assert result == GuardResult.BLOCK

    def test_detect_api_key_assignment(self):
        code = 'API_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"'
        result = guardrails.run_all_checks(code)
        assert result in (GuardResult.BLOCK, GuardResult.WARN)

    def test_detect_password_in_url(self):
        code = 'url = "postgres://user:secretpass123@localhost:5432/db"'
        result = guardrails.run_all_checks(code)
        assert result in (GuardResult.BLOCK, GuardResult.WARN)

    def test_clean_code_passes(self):
        code = '''def hello():
    name = "World"
    return f"Hello, {name}!"
'''
        result = guardrails.run_all_checks(code)
        assert result == GuardResult.PASS

    def test_env_variable_placeholder_passes(self):
        code = 'API_KEY = os.environ.get("API_KEY")'
        result = guardrails.run_all_checks(code)
        assert result == GuardResult.PASS


class TestSQLInjectionDetection:
    def test_detect_fstring_sql(self):
        code = 'query = f"SELECT * FROM users WHERE name = \'%s\'" % user_id'
        result = guardrails.run_all_checks(code)
        assert result != GuardResult.PASS

    def test_detect_format_sql(self):
        code = 'query = "WHERE id = {}".format(user_id) + " SELECT"'
        result = guardrails.run_all_checks(code)
        assert result != GuardResult.PASS

    def test_parameterized_query_passes(self):
        code = 'query = "SELECT * FROM users WHERE id = :user_id"'
        result = guardrails.run_all_checks(code)
        assert result == GuardResult.PASS


class TestDangerousCalls:
    def test_detect_os_system(self):
        code = 'os.system("rm -rf /")'
        result = guardrails.run_all_checks(code)
        assert result != GuardResult.PASS

    def test_detect_eval(self):
        code = "result = eval(user_input)"
        result = guardrails.run_all_checks(code)
        assert result != GuardResult.PASS

    def test_detect_exec(self):
        code = "exec(compile(user_input))"
        result = guardrails.run_all_checks(code)
        assert result != GuardResult.PASS

    def test_detect_pickle_loads(self):
        code = "data = pickle.loads(user_data)"
        result = guardrails.run_all_checks(code)
        assert result != GuardResult.PASS

    def test_safe_subprocess_passes(self):
        code = 'subprocess.run(["ls", "-la"])'
        result = guardrails.run_all_checks(code)
        assert result == GuardResult.PASS


class TestPRPolicy:
    def test_valid_branch_passes(self):
        result, msg = guardrails.check_pr_policy(
            "test-repo", "teammatex/feature-123", ["src/main.py"]
        )
        assert result == GuardResult.PASS

    def test_non_teammatex_branch_warns(self):
        result, msg = guardrails.check_pr_policy(
            "test-repo", "feature-123", ["src/main.py"]
        )
        assert result == GuardResult.WARN

    def test_too_many_files_warns(self):
        files = [f"src/file_{i}.py" for i in range(51)]
        result, msg = guardrails.check_pr_policy(
            "test-repo", "teammatex/big-change", files
        )
        assert result == GuardResult.WARN

    def test_critical_files_warn(self):
        result, msg = guardrails.check_pr_policy(
            "test-repo", "teammatex/infra-update",
            ["infra/terraform/main.tf", "src/app.py"],
        )
        assert result == GuardResult.WARN

    def test_deploy_freeze_blocks(self):
        result, msg = guardrails.check_pr_policy(
            "test-repo", "teammatex/hotfix", ["src/main.py"], is_deploy_freeze=True,
        )
        assert result == GuardResult.BLOCK

    def test_safe_files_pass(self):
        result, msg = guardrails.check_pr_policy(
            "test-repo", "teammatex/docs-update", ["docs/README.md", "docs/guide.md"],
        )
        assert result == GuardResult.PASS


class TestCombinedFindings:
    def test_multiple_secrets_return_first_block(self):
        code = 'AWS_KEY = "AKIA1234567890ABCDEF"\nAPI_TOKEN = "sk-abcdefghijklmnopqrstuvwxyz123456"'
        result = guardrails.run_all_checks(code)
        assert result == GuardResult.BLOCK

    def test_multiple_high_severity(self):
        code = 'query = f"SELECT * FROM users WHERE id = {uid}"\neval(user_input)'
        result = guardrails.run_all_checks(code)
        assert result in (GuardResult.WARN, GuardResult.BLOCK)

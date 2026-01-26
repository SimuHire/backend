from app.api.dependencies import github_native
from app.integrations.github.client import GithubClient


def test_actions_runner_singleton_reused_and_custom_client_gets_new_runner():
    github_native._github_client_singleton.cache_clear()
    github_native._actions_runner_singleton.cache_clear()

    default_client = github_native.get_github_client()
    runner1 = github_native.get_actions_runner(default_client)
    runner2 = github_native.get_actions_runner(default_client)

    assert runner1 is runner2
    assert runner1.client is default_client
    assert (
        runner1.workflow_file
        == github_native.settings.github.GITHUB_ACTIONS_WORKFLOW_FILE
    )

    custom_client = GithubClient(
        base_url="https://api.github.com", token="custom-token", default_org="org"
    )
    custom_runner1 = github_native.get_actions_runner(custom_client)
    custom_runner2 = github_native.get_actions_runner(custom_client)

    assert custom_runner1.client is custom_client
    assert custom_runner2.client is custom_client
    # Custom clients should not use the global singleton cache.
    assert custom_runner1 is not custom_runner2

    github_native._github_client_singleton.cache_clear()
    github_native._actions_runner_singleton.cache_clear()
